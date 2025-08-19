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
    page_icon="🎓",
    layout="wide"
)

# Your Google Apps Script Web App URL
# GOOGLE_APPS_SCRIPT_URL = os.getenv("GOOGLE_APPS_SCRIPT_URL")

# Categories for video classification
CATEGORIES = [
    "News", "Politics", "Music, Singing, & Dancing", "Comedy", "Sports", 
    "Film & Animation", "Pets & Animals", "Entertainment & Shows", "Gaming", 
    "Science & Technology", "Autos & Vehicles", "Education", "Outfit, Style, & Howto", 
    "Nonprofits & Activism", "Travel & Events", "People & Blogs", "Food", 
    "Relationship", "Family", "Beauty Care", "Daily Life", "Drama", 
    "Lipsync", "Fitness & Health", "Society"
]

# st.write("Secrets:", st.secrets)
GOOGLE_APPS_SCRIPT_URL = st.secrets["GOOGLE_APPS_SCRIPT_URL"]
models = st.secrets["LLM_MODELS"]
PROLIFIC_COMPLETION_CODE = st.secrets["PROLIFIC_COMPLETION_CODE"]

# models_str = os.getenv("LLM_MODELS", "")
# model_idx = int(os.getenv("MODEL_IDX", 0))
model_idx = int(st.secrets["MODEL_IDX"])
if isinstance(models, str):
    models = models.split(",")
else:
    st.error("LLM_MODELS should be a comma-separated string in secrets.toml or .env file.")

LLM_MODEL = models[model_idx]


# # Convert string to list
# LLM_MODELS = [m.strip() for m in models_str.split(",") if m.strip()]
# if not LLM_MODELS:
#     st.error("No LLM models configured. Please check your .env file.")
#     st.stop()
# LLM_MODEL = LLM_MODELS[model_idx]
# print(f"Using LLM Model: {LLM_MODEL}")
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

VIDEO_SAMPLE_SIZE = st.secrets["VIDEO_SAMPLE_SIZE"]
LOAD_RAMDOM = st.secrets["LOAD_RAMDOM"]
# int(os.getenv("VIDEO_SAMPLE_SIZE", 50))  # Default to 50 if not set
# LOAD_RAMDOM = os.getenv("LOAD_RAMDOM", "False").lower() == "true"


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
    """Introduction and consent page"""
    # Research Study Header with Logo
    st.markdown("""
    <div style="text-align: center; padding: 15px 0;">
        <div style="font-size: 3em; margin-bottom: 8px;">🎓</div>
        <h1 style="color: #1f4e79; margin: 0; font-size: 2.2em;">Video Summary Feedback Study</h1>
        <p style="color: #666; margin: 3px 0; font-size: 1em;">Max Planck Institute for Software Systems • Germany</p>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("---")
    
    st.markdown("""
    ### Welcome to Our Research Study

    Dear participant,

    This survey aims to understand the efficacy of multimodal language models in summarizing short-format videos. During the survey, you will be properly guided through different sections. We will record your responses given during the survey.

    This study is being conducted by academic researchers from the Max Planck Institute for Software Systems, Germany. Your valuable opinion expressed in this survey may contribute to important research findings. We request you to read the instructions carefully and answer all questions thoughtfully.

    **Privacy & Data Protection:**
    - Results may be published in research forums, but only in aggregate forms (averages, totals)
    - No personal information will be published or shared
    - All information will be protected to the greatest extent allowed by law
    - Data will be kept secured during and after the survey

    **Your Rights:**
    - Participation is completely voluntary
    - You may withdraw at any time without penalty
    - Your responses will remain anonymous
    - You can request data deletion by contacting the researchers
    """)
    
    st.markdown("---")
    st.markdown("**Note:** All fields marked with * are mandatory.")
    
    # Compact layout for ID and consent
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("👤 Participant Information")
        prolific_id = st.text_input("Prolific ID*", 
                                   placeholder="Enter your Prolific ID",
                                   help="Please enter your complete Prolific ID (typically 24 characters)")
        
        # Validate Prolific ID
        prolific_id_valid = False
        if prolific_id:
            if len(prolific_id) < 10:
                st.error("⚠️ Prolific ID seems too short. Please ensure you entered the complete ID.")
            elif len(prolific_id) > 30:
                st.error("⚠️ Prolific ID seems too long. Please check your entry.")
            elif not prolific_id.replace('-', '').replace('_', '').isalnum():
                st.error("⚠️ Prolific ID should contain only letters, numbers, hyphens, and underscores.")
            else:
                prolific_id_valid = True
                st.success("✅ Prolific ID format looks correct.")
    
    with col2:
        st.subheader("📋 Informed Consent")
        
        # Clear consent checkbox with better formatting
        consent = st.checkbox(
            label="**I provide my informed consent to participate***",
            value=False,
            help="Check this box to indicate your agreement to participate"
        )
        
        if consent:
            st.markdown("""
            <div style="background-color: #e8f5e8; padding: 10px; border-radius: 5px; border-left: 4px solid #4CAF50; color: #2e7d32;">
                <strong>✅ Consent Acknowledged</strong><br>
                <span style="color: #2e7d32;">By checking this box, you confirm that you:</span>
                <ul style="margin: 5px 0; color: #2e7d32;">
                    <li>Have read and understood the study information</li>
                    <li>Voluntarily agree to participate in this research</li>
                    <li>Understand your participation is voluntary and anonymous</li>
                    <li>Know you can withdraw at any time</li>
                </ul>
            </div>
            """, unsafe_allow_html=True)
    
    # Enable button only when all conditions are met
    can_proceed = prolific_id and prolific_id_valid and consent
    
    st.markdown("---")
    
    if st.button("🚀 Begin Study", disabled=not can_proceed, type="primary", use_container_width=True):
        if can_proceed:
            st.session_state.prolific_id = prolific_id
            st.session_state.consent_given = True
            
            # Load video data
            video_list_file = "data/required_videos.txt"
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
            if not prolific_id:
                st.error("⚠️ Please enter your Prolific ID.")
            elif not prolific_id_valid:
                st.error("⚠️ Please enter a valid Prolific ID.")
            elif not consent:
                st.error("⚠️ Please provide your informed consent to continue.")

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
    
    # Prominent instructions at the top of the page
    st.markdown("""
    <div style="background-color: #e3f2fd; padding: 15px; border-radius: 10px; border-left: 5px solid #2196f3; margin-bottom: 20px;">
        <h3 style="color: #1976d2; margin: 0 0 8px 0; font-size: 1.3em;">📋 Instructions</h3>
        <p style="color: #424242; margin: 0; font-size: 1.1em; font-weight: 500;">
            Your task is to evaluate the quality of the AI-generated summary on the right for the given short form video. Please follow these steps:
            Watch the video → Read the AI summary → Rate the summary quality → Categorize the video content → Provide detailed feedback
        </p>
    </div>
    """, unsafe_allow_html=True)
    
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
        st.markdown("**Note:** All fields marked with * are mandatory.")
        
        # Form fields outside of st.form for real-time validation
        st.markdown("📊 **How do you rate the above-written summary of the video?***")
        rating = st.radio(
            "Overall quality rating",
            options=[1, 2, 3, 4, 5],
            format_func=lambda x: f"{x} - {['Very Poor', 'Poor', 'Fair', 'Good', 'Very Good'][x-1]}",
            index=None,
            horizontal=True,
            label_visibility="collapsed",
            key=f"rating_{current_idx}"
        )
        
        # # Summary Accuracy
        # st.markdown("🎯 **How accurate is the above-written summary of the video? Please feel free to rewatch the video if you need.***")
        # accuracy = st.radio(
        #     "Summary accuracy rating",
        #     options=[1, 2, 3, 4, 5],
        #     format_func=lambda x: f"{x} - {['Very Poor', 'Poor', 'Fair', 'Good', 'Very Good'][x-1]}",
        #     index=None,
        #     horizontal=True,
        #     label_visibility="collapsed",
        #     key=f"accuracy_{current_idx}"
        # )

        accuracy = None

        # Video Category Selection
        st.markdown("📂 **Video Category***:")
        predicted_category = st.selectbox(
            "What category best describes this video?",
            options=[""] + CATEGORIES,
            index=0,
            help="Select the most appropriate category for this video content",
            label_visibility="collapsed",
            key=f"category_{current_idx}"
        )
        
        # Detailed Feedback
        comments = st.text_area(
            "💬 **Detailed Feedback***:",
            placeholder="Briefly explain your rating and summary accuracy scores you provided. What was accurate/inaccurate? What was missing?",
            height=100,
            help="This field is mandatory. Please explain your ratings.",
            key=f"comments_{current_idx}"
        )
        
        # Check if all required fields are filled
        all_fields_filled = (
            rating is not None and 
            # accuracy is not None and 
            predicted_category and predicted_category != ""
            and comments.strip() != ""
        )
        
        # Show validation messages in real-time
        if not all_fields_filled:
            missing_fields = []
            if rating is None:
                missing_fields.append("Overall rating")
            if accuracy is None:
                missing_fields.append("Summary accuracy")
            if not predicted_category or predicted_category == "":
                missing_fields.append("Video category")
            if not comments.strip():
                missing_fields.append("Detailed feedback")
            
            if missing_fields:
                st.warning(f"⚠️ Please complete: {', '.join(missing_fields)}")
        
        # Determine button text and action based on video position
        is_last_video = current_idx >= total_videos - 1
        
        if is_last_video:
            button_text = "✅ Submit & Complete Study"
            button_help = "Submit your feedback and complete the study"
        else:
            button_text = "➡️ Next Video"
            button_help = f"Continue to video {current_idx + 2} of {total_videos}"
        
        # Action button
        if st.button(
            button_text,
            type="primary" if all_fields_filled else "secondary",
            disabled=not all_fields_filled,
            help=button_help,
            use_container_width=True,
            key=f"submit_btn_{current_idx}"
        ):
            if all_fields_filled:
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
                
                # Move to next video or finish
                if is_last_video:
                    # This is the last video, proceed to submit all data
                    submit_all_data()
                else:
                    # Move to next video
                    st.session_state.current_video_index += 1
                    st.session_state.video_start_time = time.time()  # Reset timer for next video
                    st.rerun()

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
    """Final summary page"""
    st.markdown("""
    <div style="text-align: center; padding: 20px 0;">
        <div style="font-size: 4em; margin-bottom: 10px;">🎉</div>
        <h1 style="color: #1f4e79; margin: 0;">Study Complete!</h1>
        <p style="color: #666; font-size: 1.2em;">Thank you for your participation in the Video Summary Feedback Study</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Show submission status
    if st.session_state.submission_complete:
        st.success("✅ Your responses have been successfully submitted!")
        if st.session_state.feedback_data:
            st.markdown("### ✅ Next Steps")
            st.success(
                f"""
                Thank you for your responses!  
                To complete the survey, please enter the following code on the Prolific website:  

                **{PROLIFIC_COMPLETION_CODE}**
                """
            )

            # Show summary of responses
            st.subheader("📊 Response Summary")
            df = pd.DataFrame(st.session_state.feedback_data)

            # Key stats
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Videos Reviewed", len(df))
            with col2:
                avg_rating = df['rating'].mean()
                st.metric("Avg. Rating", f"{avg_rating:.1f}/5")
            with col3:
                total_time = df['time_spent'].sum()
                st.metric("Time Spent", f"{total_time:.0f}s")

            st.markdown("---")
            

            # Optional details
            with st.expander("📋 View All Responses"):
                display_df = df[['video_name', 'rating', 'accuracy', 'predicted_category', 'comments']]
                st.dataframe(display_df, use_container_width=True)

            # Backup option
            csv = df.to_csv(index=False)
            st.download_button(
                "📥 Download Responses",
                data=csv,
                file_name=f"feedback_backup_{st.session_state.prolific_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
                mime="text/csv"
            )
    else:
        st.error("❌ There were issues submitting some responses.")
    
    

    
    
    
    # # Optional: Reset study button for testing
    # if st.button("🔄 Start New Study Session", help="For testing purposes only"):
    #     # Reset all session state
    #     for key in list(st.session_state.keys()):
    #         del st.session_state[key]
    #     st.rerun()

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