import streamlit as st
import pandas as pd
import requests
from datetime import datetime
import uuid
import json
import time
import os
import random
from dotenv import load_dotenv

# Load the .env file
load_dotenv()

# Page config
st.set_page_config(
    page_title="Video Summary Feedback Tool",
    page_icon="🎥",
    layout="wide"
)

# Your Google Apps Script Web App URL
GOOGLE_APPS_SCRIPT_URL = os.getenv("GOOGLE_APPS_SCRIPT_URL")

# Categories for video classification
CATEGORIES = [
    "News", "Politics", "Music, Singing, & Dancing", "Comedy", "Sports", 
    "Film & Animation", "Pets & Animals", "Entertainment & Shows", "Gaming", 
    "Science & Technology", "Autos & Vehicles", "Education", "Outfit, Style, & Howto", 
    "Nonprofits & Activism", "Travel & Events", "People & Blogs", "Food", 
    "Relationship", "Family", "Beauty Care", "Daily Life", "Drama", 
    "Lipsync", "Fitness & Health", "Society"
]

models_str = os.getenv("LLM_MODELS", "")
model_idx = int(os.getenv("MODEL_IDX", 0))
# Convert string to list
LLM_MODELS = [m.strip() for m in models_str.split(",") if m.strip()]
if not LLM_MODELS:
    st.error("No LLM models configured. Please check your .env file.")
    st.stop()
LLM_MODEL = LLM_MODELS[model_idx]
print(f"Using LLM Model: {LLM_MODEL}")
# LLM Model (hardcoded for now)
# LLM_MODELS = os.getenv("LLM_MODELS", "gemini,internvl,qwenvl").split(",")

csv_path_dict = {
    "gemini": "gemini.csv",
    "internvl": "internvl.csv",
    "qwenvl": "qwenvl.csv"
}
file_name = csv_path_dict[LLM_MODEL]

with open("data/video_name_to_id.json", "r") as f:
    video_name_to_id = json.load(f)

VIDEO_SAMPLE_SIZE = int(os.getenv("VIDEO_SAMPLE_SIZE", 50))  # Default to 50 if not set
LOAD_RAMDOM = os.getenv("LOAD_RAMDOM", "False").lower() == "true"


def load_video_data(video_list_file):
    """Load video data from text file and corresponding CSV"""
    videos = []
    
    # Read video list from text file
    if os.path.exists(video_list_file):
        with open(video_list_file, 'r') as f:
            video_names = [line.strip() for line in f if line.strip()]
    else:
        st.error(f"Video list file not found: {video_list_file}")
        return []
    
    # Load corresponding CSV file
    csv_file = f"data/csv/{LLM_MODEL}/{file_name}"

    # Sample video_names for testing
    if LOAD_RAMDOM:
        video_names = random.sample(video_names, VIDEO_SAMPLE_SIZE)
    else:
        video_names = video_names[:VIDEO_SAMPLE_SIZE]
    
    if os.path.exists(csv_file):
        df = pd.read_csv(csv_file)
        
        for video_name in video_names:
            # Find matching row in CSV
            matching_row = df[df['video_id'] == int(video_name)]
            if not matching_row.empty:
                row = matching_row.iloc[0]
                videos.append({
                    "name": video_name,
                    "drive_id": video_name_to_id[video_name],
                    "summary": row.get('summary', ''),
                    "true_category": row.get('category', 'Unknown')
                })
    else:
        st.error(f"CSV file not found: {csv_file}")
        return []
    
    return videos

def append_to_public_sheet(data, max_retries=3):
    """Append data to public Google Sheet using Google Apps Script with retry logic"""
    
    for attempt in range(max_retries):
        try:
            # Prepare data with consistent column order - make sure this matches your Google Sheet headers
            payload = {
                'timestamp': data['timestamp'],
                'prolific_id': data['prolific_id'],
                'session_id': data['session_id'],
                'video_name': data['video_name'],
                'rating': data['rating'],
                'accuracy': data['accuracy'],
                'predicted_category': data['predicted_category'],
                'true_category': data['true_category'],
                'comments': data['comments'],
                'llm_model': data['llm_model'],
                'time_spent': data['time_spent']
            }
            
            # Send POST request to Google Apps Script with longer timeout
            response = requests.post(
                GOOGLE_APPS_SCRIPT_URL,
                json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'StreamlitApp/1.0'
                },
                timeout=30,
                verify=True
            )
            
            # Check response
            if response.status_code == 200:
                try:
                    result = response.json()
                    if result.get('status') == 'success':
                        return True, "Success"
                    else:
                        error_msg = result.get('message', 'Unknown error from Google Apps Script')
                        return False, f"Script error: {error_msg}"
                except json.JSONDecodeError:
                    if "success" in response.text.lower():
                        return True, "Success (HTML response)"
                    else:
                        return False, f"Invalid JSON response: {response.text[:200]}..."
            else:
                error_msg = f"HTTP {response.status_code}: {response.text[:200]}..."
                if attempt < max_retries - 1:
                    st.warning(f"Attempt {attempt + 1} failed. Retrying in 2 seconds...")
                    time.sleep(2)
                    continue
                return False, error_msg
                
        except requests.exceptions.Timeout:
            error_msg = f"Request timed out (attempt {attempt + 1}/{max_retries})"
            if attempt < max_retries - 1:
                st.warning(f"Timeout on attempt {attempt + 1}. Retrying in 3 seconds...")
                time.sleep(3)
                continue
            return False, "Request timed out after multiple attempts"
            
        except requests.exceptions.ConnectionError:
            error_msg = f"Connection error (attempt {attempt + 1}/{max_retries})"
            if attempt < max_retries - 1:
                st.warning(f"Connection failed on attempt {attempt + 1}. Retrying in 3 seconds...")
                time.sleep(3)
                continue
            return False, "Connection failed after multiple attempts"
            
        except requests.exceptions.RequestException as e:
            error_msg = f"Network error: {str(e)}"
            if attempt < max_retries - 1:
                st.warning(f"Network error on attempt {attempt + 1}. Retrying...")
                time.sleep(2)
                continue
            return False, error_msg
            
        except Exception as e:
            return False, f"Unexpected error: {str(e)}"
    
    return False, "Max retries exceeded"

def get_video_embed_url(drive_id):
    return f"https://drive.google.com/file/d/{drive_id}/preview"

# Initialize session state
if 'feedback_data' not in st.session_state:
    st.session_state.feedback_data = []
if 'session_id' not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())[:8]
if 'current_video_index' not in st.session_state:
    st.session_state.current_video_index = 0
if 'videos' not in st.session_state:
    st.session_state.videos = []
if 'page' not in st.session_state:
    st.session_state.page = 'intro'
if 'prolific_id' not in st.session_state:
    st.session_state.prolific_id = ''
if 'consent_given' not in st.session_state:
    st.session_state.consent_given = False
if 'video_start_time' not in st.session_state:
    st.session_state.video_start_time = None
if 'submission_complete' not in st.session_state:
    st.session_state.submission_complete = False

def intro_page():
    """Introduction and consent page - Made more compact"""
    st.title("🎥 Video Summary Feedback Study")
    st.markdown("**Max Planck Institute for Informatics**")
    
    st.markdown("""
    ## Study Overview
    
    Help us improve AI-generated video summaries by watching short videos and rating their summaries.
    
    **What you'll do:** Watch videos → Read AI summaries → Rate accuracy → Categorize content
    
    **Time:** ~10-15 minutes total
    
    **Privacy:** Anonymous responses, research use only, withdraw anytime
    """)
    
    # Compact layout for ID and consent
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("👤 Participant ID")
        prolific_id = st.text_input("Prolific ID*", 
                                   placeholder="Enter your Prolific ID")
    
    with col2:
        st.subheader("📋 Consent")
        consent = st.checkbox("""
        I consent to participate in this research study. 
        I understand my participation is voluntary, 
        responses are anonymous, and I can withdraw anytime.
        """)
    
    if st.button("🚀 Begin Study", disabled=not (prolific_id and consent), type="primary"):
        if prolific_id and consent:
            st.session_state.prolific_id = prolific_id
            st.session_state.consent_given = True
            
            # Load video data
            video_list_file = "data/common_videos_list.txt"
            videos = load_video_data(video_list_file)
            
            if videos:
                # Randomize video order
                random.shuffle(videos)
                st.session_state.videos = videos
                st.session_state.page = 'survey'
                st.session_state.video_start_time = time.time()
                st.rerun()
            else:
                st.error("No videos found. Please contact the researchers.")
        else:
            st.error("Please enter your Prolific ID and provide consent to continue.")

def survey_page():
    """Main survey page with video feedback"""
    if not st.session_state.videos:
        st.error("No videos loaded. Please restart the study.")
        return
    
    current_idx = st.session_state.current_video_index
    total_videos = len(st.session_state.videos)
    
    # Progress indicator
    st.progress((current_idx + 1) / total_videos)
    st.write(f"Video {current_idx + 1} of {total_videos}")
    
    current_video = st.session_state.videos[current_idx]
    
    # Initialize video start time if not set
    if st.session_state.video_start_time is None:
        st.session_state.video_start_time = time.time()
    
    # Create layout: larger video area, smaller summary/feedback area
    col1, col2 = st.columns([1.5, 2])
    
    with col1:
        st.subheader(f"📹 Video {current_idx + 1}")
        
        # Video player with increased size
        if current_video['drive_id']:
            video_url = get_video_embed_url(current_video['drive_id'])
            
            video_html = f"""
            <div style="border: 2px solid #ddd; border-radius: 10px; overflow: hidden;">
                <iframe src="{video_url}" 
                        width="100%" 
                        height="500" 
                        frameborder="0" 
                        allowfullscreen="true"
                        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture">
                </iframe>
            </div>
            """
            st.components.v1.html(video_html, height=520)
        else:
            st.warning("Video not available")
    
    with col2:
        st.subheader("🤖 Video Summary")
        st.text_area("", value=current_video['summary'], height=200, disabled=True)
        
        # Feedback form
        st.subheader("📝 Your Feedback")
        
        with st.form("feedback_form"):
            # Overall Rating
            st.markdown("📊 **Overall Rating***:")
            rating = st.radio(
                "Rate the overall quality of the video summary",
                options=[1, 2, 3, 4, 5],
                format_func=lambda x: f"{['Very Poor', 'Poor', 'Ok', 'Good', 'Very Good'][x-1]}",
                index=2,
                horizontal=True,
                label_visibility="collapsed"
            )
            
            # Summary Accuracy
            st.markdown("🎯 **Summary Accuracy***:")
            accuracy = st.radio(
                "Rate the accuracy of the video summary",
                options=[1, 2, 3, 4, 5],
                format_func=lambda x: f"{['Very Bad', 'Bad', 'Moderate', 'Good', 'Very Good'][x-1]}",
                index=2,
                horizontal=True,
                label_visibility="collapsed"
            )

            # Video Category Selection
            st.markdown("📂 **Video Category***:")
            predicted_category = st.selectbox(
                "What category best describes this video?",
                options=[""] + CATEGORIES,
                index=0,
                help="Select the most appropriate category for this video content",
                label_visibility="collapsed"
            )
            
            # Detailed Feedback
            comments = st.text_area(
                "💬 Detailed Feedback*:",
                placeholder="Briefly explain your rating and summary accuracy scores you provided. What was accurate/inaccurate? What was missing?",
                height=100,
                help="This field is mandatory. Please explain your ratings."
            )
            
            # Form validation and submission
            if current_idx < total_videos - 1:
                submitted = st.form_submit_button("➡️ Next Video", type="primary")
            else:
                submitted = st.form_submit_button("✅ Submit & Complete Study", type="primary")
            
            if submitted:
                # Validation
                if not comments.strip():
                    st.error("⚠️ Detailed feedback is mandatory. Please provide your explanation.")
                elif not predicted_category:
                    st.error("⚠️ Please select a video category.")
                else:
                    # Calculate time spent on this video
                    time_spent = time.time() - st.session_state.video_start_time if st.session_state.video_start_time else 0
                    
                    # Prepare feedback data with consistent ordering
                    feedback_data = {
                        'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                        'prolific_id': st.session_state.prolific_id,
                        'session_id': st.session_state.session_id,
                        'video_name': current_video['name'],
                        'rating': rating,
                        'accuracy': accuracy,
                        'predicted_category': predicted_category,
                        'true_category': current_video['true_category'],
                        'comments': comments,
                        'llm_model': LLM_MODEL,
                        'time_spent': round(time_spent, 2)
                    }
                    
                    # Add to session state
                    st.session_state.feedback_data.append(feedback_data)
                    
                    # Move to next video or finish and submit
                    if current_idx < total_videos - 1:
                        st.session_state.current_video_index += 1
                        st.session_state.video_start_time = time.time()  # Reset timer for next video
                        st.rerun()
                    else:
                        # This is the last video, proceed to submit all data
                        submit_all_data()

def submit_all_data():
    """Submit all collected data to Google Sheets"""
    if not st.session_state.feedback_data:
        st.error("No data to submit")
        return
    
    success_count = 0
    total_count = len(st.session_state.feedback_data)
    
    # Show submission progress
    st.subheader("📤 Submitting Your Responses...")
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    for i, feedback in enumerate(st.session_state.feedback_data):
        status_text.text(f"Submitting response {i+1}/{total_count}...")
        progress_bar.progress((i + 1) / total_count)
        
        success, message = append_to_public_sheet(feedback)
        if success:
            success_count += 1
        else:
            st.error(f"Failed to submit response {i+1}: {message}")
        
        time.sleep(0.5)  # Small delay between submissions
    
    # Update submission status
    if success_count == total_count:
        st.session_state.submission_complete = True
        st.success(f"✅ Successfully submitted all {success_count} responses!")
        st.balloons()
    elif success_count > 0:
        st.warning(f"⚠️ Submitted {success_count}/{total_count} responses. Some may have failed.")
        st.session_state.submission_complete = True
    else:
        st.error("❌ Failed to submit responses. Please contact the researchers.")
        st.session_state.submission_complete = False
    
    # Move to summary page
    st.session_state.page = 'summary'
    time.sleep(2)  # Brief pause before redirect
    st.rerun()

def summary_page():
    """Final summary page - no additional submit button"""
    st.title("🎉 Study Complete!")
    st.markdown("Thank you for your participation in the Video Summary Feedback Study.")
    
    # Show submission status
    if st.session_state.submission_complete:
        st.success("✅ Your responses have been successfully submitted!")
    else:
        st.error("❌ There were issues submitting some responses.")
    
    # Show summary of responses
    st.subheader("📊 Your Response Summary")
    if st.session_state.feedback_data:
        df = pd.DataFrame(st.session_state.feedback_data)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Videos Reviewed", len(df))
        with col2:
            avg_rating = df['rating'].mean()
            st.metric("Average Rating", f"{avg_rating:.1f}/5")
        with col3:
            total_time = df['time_spent'].sum()
            st.metric("Total Time", f"{total_time:.0f}s")
        
        # Show responses table
        with st.expander("📋 View All Responses"):
            display_df = df[['video_name', 'rating', 'accuracy', 'predicted_category', 'comments']]
            st.dataframe(display_df, use_container_width=True)
        
        # Download backup option
        csv = df.to_csv(index=False)
        st.download_button(
            "📥 Download Response Backup",
            data=csv,
            file_name=f"feedback_backup_{st.session_state.prolific_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            help="Download your responses as a backup file"
        )
    
    st.markdown("---")
    st.markdown("### 📝 Next Steps")
    st.markdown("""
    - You can now close this browser window
    - Your participation is complete
    - Thank you for contributing to AI research!
    """)
    
    # Optional: Reset study button for testing
    if st.button("🔄 Start New Study Session", help="For testing purposes only"):
        # Reset all session state
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

def main():
    """Main application logic"""
    
    # Route to appropriate page
    if st.session_state.page == 'intro':
        intro_page()
    elif st.session_state.page == 'survey':
        survey_page()
    elif st.session_state.page == 'summary':
        summary_page()
    else:
        intro_page()

if __name__ == "__main__":
    main()