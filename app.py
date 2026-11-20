import streamlit as st
import plotly.graph_objects as go

from backend import (
    chat_with_ai, analyze_image, transcribe_audio, analyze_video,
    reconstruct_sparse_3d, build_pdf_report, annotate_image,
    get_service_status,
)
from database import (
    init_db, create_project, list_projects, save_message, get_messages,
    save_inspection, list_inspections,
)

st.set_page_config(
    page_title="InfraTwin AI",
    page_icon="🏗️",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap');
html, body, [class*="css"] {font-family: 'DM Sans', sans-serif;}
.block-container {padding-top: 1.35rem; max-width: 1450px;}
[data-testid="stSidebar"] {border-right: 1px solid rgba(128,128,128,.18);}
.hero {padding: 1.45rem 1.6rem; border: 1px solid rgba(128,128,128,.22);
       border-radius: 18px; margin-bottom: 1.2rem;
       background: linear-gradient(115deg, rgba(35,125,145,.17), rgba(48,120,88,.09));}
.hero h1 {margin: 0 0 .35rem 0; font-size: 2.05rem; letter-spacing: -.04em;}
.hero p {margin: 0; opacity: .76;}
.metric {border: 1px solid rgba(128,128,128,.22); border-radius: 14px; padding: 14px 16px;}
.muted {opacity: .68; font-size: .88rem;}
div[data-testid="stChatMessage"] {border-radius: 14px;}
.stButton button {border-radius: 10px;}
</style>
""", unsafe_allow_html=True)

init_db()

if "project_id" not in st.session_state:
    st.session_state.project_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_report" not in st.session_state:
    st.session_state.last_report = None

def open_project(project_id):
    st.session_state.project_id = project_id
    st.session_state.messages = get_messages(project_id)

def new_project():
    pid = create_project("New inspection")
    open_project(pid)

if st.session_state.project_id is None:
    new_project()

with st.sidebar:
    st.markdown("## 🏗️ InfraTwin AI")
    st.caption("Infrastructure intelligence workspace")
    if st.button("＋ New inspection", use_container_width=True, type="primary"):
        new_project()
        st.rerun()

    st.divider()
    st.markdown("**Inspection workspaces**")
    projects = list_projects()
    if not projects:
        st.caption("No saved workspaces yet.")
    for project in projects[:15]:
        if st.button(f"📁 {project['title'][:28]}", key=f"p_{project['id']}", use_container_width=True):
            open_project(project["id"])
            st.rerun()

    st.divider()
    st.markdown("**AI services**")
    status = get_service_status()
    st.caption("Groq text model")
if status["text"]:
    st.success("Configured")
else:
    st.error("API key missing")

st.caption("Groq vision model")
if status["vision"]:
    st.success("Configured")
else:
    st.warning("Check vision model")

st.caption("Speech transcription")
if status["text"]:
    st.success("Available with Groq key")
else:
    st.warning("Needs API key")
    st.divider()
    st.caption("Prototype decision-support software. Engineering findings require professional verification.")

st.markdown("""
<div class="hero">
  <h1>InfraTwin AI</h1>
  <p>Inspect infrastructure evidence, document possible defects, and build a spatial record of what you find.</p>
</div>
""", unsafe_allow_html=True)

saved = list_inspections(limit=100)
c1, c2, c3, c4 = st.columns(4)
for col, label, value in [
    (c1, "Saved analyses", len(saved)),
    (c2, "Inspection workspaces", len(projects)),
    (c3, "Input modes", "Image · Audio · Video"),
    (c4, "3D output", "Sparse point cloud"),
]:
    with col:
        st.markdown(f'<div class="metric"><div class="muted">{label}</div><h3 style="margin:.2rem 0 0">{value}</h3></div>', unsafe_allow_html=True)

tabs = st.tabs([
    "💬 AI assistant", "🖼️ Image inspection", "🎙️ Speech notes",
    "🎞️ Video inspection", "🧊 3D reconstruction", "📑 Reports & history"
])

# AI assistant
with tabs[0]:
    st.subheader("Engineering inspection assistant")
    st.caption("Ask about inspection planning, defect terminology, evidence documentation, or next steps.")
    for item in st.session_state.messages:
        with st.chat_message(item["role"]):
            st.markdown(item["content"])
    prompt = st.chat_input("Ask InfraTwin AI a question…", key="main_chat")
    if prompt:
        save_message(st.session_state.project_id, "user", prompt)
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                try:
                    answer = chat_with_ai(st.session_state.messages)
                except Exception as exc:
                    answer = f"AI request failed: {exc}"
            st.markdown(answer)
        save_message(st.session_state.project_id, "assistant", answer)
        st.session_state.messages.append({"role": "assistant", "content": answer})

# Image inspection
with tabs[1]:
    st.subheader("Image-based infrastructure inspection")
    st.write("Upload a clear image of a pipe, joint, bridge element, building component or other asset.")
    image_file = st.file_uploader("Infrastructure image", type=["jpg", "jpeg", "png", "webp"], key="image_upload")
    image_question = st.text_input("Inspection focus (optional)", placeholder="e.g. Focus on corrosion around the pipe joint", key="image_question")
    if image_file:
        st.image(image_file, caption=image_file.name, use_container_width=True)
        if st.button("Analyze image", type="primary", key="analyze_image"):
            with st.spinner("Analyzing image with the vision model…"):
                try:
                    result = analyze_image(image_file.getvalue(), image_file.name, image_question)
                    st.session_state.image_result = result
                    save_inspection(
                        title=f"Image: {image_file.name}",
                        modality="image",
                        result=result["report"],
                    )
                except Exception as exc:
                    st.error(f"Image analysis failed: {exc}")
        result = st.session_state.get("image_result")
        if result:
            st.markdown("### Inspection observations")
            st.markdown(result["report"])
            annotated = annotate_image(image_file.getvalue(), result.get("findings", []))
            st.image(annotated, caption="AI-suggested regions (approximate, verify manually)", use_container_width=True)
            st.download_button("Download annotated image", annotated, file_name="infratwin_annotated.png", mime="image/png")

# Speech
with tabs[2]:
    st.subheader("Speech-to-text inspection notes")
    st.write("Upload a spoken inspection note. Groq Whisper supports multilingual transcription.")
    audio_file = st.file_uploader("Audio recording", type=["wav", "mp3", "m4a", "ogg", "flac", "webm", "mp4"], key="audio_upload")
    language = st.selectbox("Audio language", ["Auto detect", "English", "Urdu", "Sindhi"], key="audio_language")
    if audio_file and st.button("Transcribe recording", type="primary"):
        if audio_file.size > 25 * 1024 * 1024:
            st.error("This upload is larger than the 25 MB starter limit. Please compress or shorten it.")
        else:
            with st.spinner("Transcribing audio…"):
                try:
                    transcript = transcribe_audio(audio_file.getvalue(), audio_file.name, language)
                    st.session_state.transcript = transcript
                    save_inspection(f"Speech note: {audio_file.name}", "audio", transcript)
                except Exception as exc:
                    st.error(f"Transcription failed: {exc}")
    if st.session_state.get("transcript"):
        st.markdown("### Transcript")
        st.text_area("Recognized speech", st.session_state.transcript, height=180)
        st.download_button("Download transcript", st.session_state.transcript, "inspection_transcript.txt")
        if st.button("Turn transcript into structured inspection note"):
            with st.spinner("Structuring the note…"):
                try:
                    structured = chat_with_ai([
                        {"role": "user", "content": "Convert this transcript into a structured engineering inspection note. Separate observed facts, possible concerns, missing information, and recommended follow-up. Do not invent details:\n\n" + st.session_state.transcript}
                    ])
                    st.markdown(structured)
                    save_inspection("Structured speech inspection note", "speech-note", structured)
                except Exception as exc:
                    st.error(str(exc))

# Video
with tabs[3]:
    st.subheader("Video inspection")
    st.write("Extract representative frames from a short inspection video and analyze them for visible indications.")
    video_file = st.file_uploader("Inspection video", type=["mp4", "mov", "avi", "mkv"], key="video_upload")
    if video_file:
        st.video(video_file)
        max_frames = st.slider("Maximum frames to analyze", 2, 8, 4)
        focus = st.text_input("What should the model look for?", "Visible corrosion, cracks, deformation, leakage or damaged connections")
        if st.button("Analyze video frames", type="primary"):
            if video_file.size > 80 * 1024 * 1024:
                st.error("Video is over the 80 MB starter limit. Please trim or compress it.")
            else:
                with st.spinner("Extracting frames and analyzing…"):
                    try:
                        video_result = analyze_video(video_file.getvalue(), video_file.name, focus, max_frames)
                        st.session_state.video_result = video_result
                        save_inspection(f"Video: {video_file.name}", "video", video_result["report"])
                    except Exception as exc:
                        st.error(f"Video analysis failed: {exc}")
        video_result = st.session_state.get("video_result")
        if video_result:
            st.markdown("### Video findings")
            st.markdown(video_result["report"])
            frame_cols = st.columns(min(4, len(video_result["frames"])))
            for idx, frame in enumerate(video_result["frames"]):
                with frame_cols[idx % len(frame_cols)]:
                    st.image(frame, caption=f"Frame {idx + 1}", use_container_width=True)

# 3D reconstruction
with tabs[4]:
    st.subheader("3D reconstruction from overlapping photographs")
    st.info("This module performs experimental two-view sparse photogrammetry. It needs two sharp, overlapping photos of the same object from different viewpoints. It does not create a complete textured CAD model.")
    photos = st.file_uploader("Upload 2–8 overlapping photos", type=["jpg", "jpeg", "png"], accept_multiple_files=True, key="photos_3d")
    if photos:
        st.write(f"{len(photos)} photo(s) selected")
        preview_cols = st.columns(min(4, len(photos)))
        for i, photo in enumerate(photos):
            with preview_cols[i % len(preview_cols)]:
                st.image(photo, caption=photo.name, use_container_width=True)
    if photos and len(photos) >= 2 and st.button("Reconstruct sparse 3D point cloud", type="primary"):
        with st.spinner("Matching image features and estimating camera geometry…"):
            try:
                cloud = reconstruct_sparse_3d([p.getvalue() for p in photos[:8]])
                st.session_state.point_cloud = cloud
                save_inspection("Sparse 3D reconstruction", "3d", cloud["summary"])
            except Exception as exc:
                st.error(f"3D reconstruction failed: {exc}")
    cloud = st.session_state.get("point_cloud")
    if cloud:
        st.markdown("### Reconstructed point cloud")
        points = cloud["points"]
        fig = go.Figure(data=[go.Scatter3d(
            x=points[:, 0], y=points[:, 1], z=points[:, 2],
            mode="markers", marker=dict(size=2, color=points[:, 2], colorscale="Viridis", opacity=.8)
        )])
        fig.update_layout(
            scene=dict(aspectmode="data", xaxis_title="X", yaxis_title="Y", zaxis_title="Z"),
            margin=dict(l=0, r=0, t=10, b=0), height=560,
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(cloud["summary"])
        st.download_button("Download sparse point cloud (.ply)", cloud["ply"], "infratwin_sparse_cloud.ply", mime="application/octet-stream")

# Reports and history
with tabs[5]:
    st.subheader("Inspection records")
    records = list_inspections(limit=100)
    if not records:
        st.info("Your image, audio, video and 3D analysis records will appear here.")
    else:
        for record in records:
            with st.expander(f"{record['title']} · {record['modality']} · {record['created_at']}"):
                st.markdown(record["result"])
                pdf = build_pdf_report(record["title"], record["modality"], record["result"])
                st.download_button(
                    "Download PDF report", pdf,
                    file_name=f"infratwin_{record['id'][:8]}.pdf",
                    mime="application/pdf",
                    key=f"pdf_{record['id']}",
                )

st.divider()
st.caption("InfraTwin AI is a prototype engineering decision-support tool. AI observations are not certified diagnoses or structural safety assessments.")
