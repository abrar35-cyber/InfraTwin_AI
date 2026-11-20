import base64
import io
import json
import re
import tempfile
from pathlib import Path

import cv2
import numpy as np
import streamlit as st
from groq import Groq
from PIL import Image, ImageDraw, ImageFont
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

DEFAULT_TEXT_MODEL = "openai/gpt-oss-120b"
DEFAULT_VISION_MODEL = "qwen/qwen3.8-27b"
DEFAULT_STT_MODEL = "whisper-large-v3-turbo"

SYSTEM_PROMPT = """
You are InfraTwin AI, an engineering infrastructure inspection assistant.
Help with inspection planning, visible observations, defect terminology, and clear documentation.
Be cautious and evidence-led:
- Distinguish visible indications from confirmed defects and root causes.
- Never declare a structure safe or unsafe based only on an image or video.
- Never invent dimensions, material properties, test results, standards clauses, or certainty.
- State image limitations and recommend qualified on-site verification for safety-critical concerns.
- Use practical, concise language and separate observations from recommendations.
"""

def get_secret(name, default=None):
    try:
        return st.secrets.get(name, default)
    except Exception:
        return default

def get_client():
    key = get_secret("GROQ_API_KEY", "")
    if not key:
        raise RuntimeError("GROQ_API_KEY is missing. Add it under Streamlit app Settings → Secrets.")
    return Groq(api_key=key)

def get_service_status():
    return {
        "text": bool(get_secret("GROQ_API_KEY", "")),
        "vision": bool(get_secret("GROQ_API_KEY", "")),
    }

def chat_with_ai(messages):
    client = get_client()
    model = get_secret("GROQ_TEXT_MODEL", DEFAULT_TEXT_MODEL)
    prompt_messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for item in messages[-14:]:
        role = item.get("role")
        text = item.get("content", "")
        if role in ("user", "assistant") and isinstance(text, str):
            prompt_messages.append({"role": role, "content": text})
    response = client.chat.completions.create(
        model=model,
        messages=prompt_messages,
        temperature=0.25,
        max_completion_tokens=1600,
    )
    return response.choices[0].message.content or "No response was returned."

def _image_data_url(image_bytes):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    image.thumbnail((1600, 1600))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=88)
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}", image

def _parse_json_response(text):
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.S)
        if match:
            try:
                return json.loads(match.group(0))
            except json.JSONDecodeError:
                pass
    return {"summary": text, "findings": []}

def analyze_image(image_bytes, filename, focus=""):
    client = get_client()
    model = get_secret("GROQ_VISION_MODEL", DEFAULT_VISION_MODEL)
    data_url, image = _image_data_url(image_bytes)
    instruction = f"""
Inspect this infrastructure photograph. Focus requested by user: {focus or 'General visible inspection'}.
Return valid JSON only with this structure:
{{
 "summary": "short overall summary",
 "limitations": ["limitations"],
 "findings": [
   {{
    "label": "short possible finding",
    "severity": "Low|Medium|High|Unknown",
    "confidence": "Low|Medium|High",
    "description": "what is visibly present; avoid claiming hidden causes",
    "recommendation": "practical next check",
    "bbox": [x1,y1,x2,y2]
   }}
 ]
}}
bbox coordinates must be normalized from 0 to 1000 (left,top,right,bottom). Include a box only when a visible region can reasonably be localized. Do not invent boxes. Do not declare structural safety.
"""
    response = client.chat.completions.create(
        model=model,
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": instruction},
                {"type": "image_url", "image_url": {"url": data_url}},
            ],
        }],
        temperature=0.1,
        max_completion_tokens=1800,
    )
    raw = response.choices[0].message.content or "{}"
    data = _parse_json_response(raw)
    findings = data.get("findings", []) if isinstance(data, dict) else []
    if not isinstance(findings, list):
        findings = []
    lines = [f"**File:** {filename}", "", f"**Summary:** {data.get('summary', raw)}", ""]
    for i, finding in enumerate(findings, 1):
        if not isinstance(finding, dict):
            continue
        lines.extend([
            f"#### {i}. {finding.get('label', 'Observation')}",
            f"- **Severity indication:** {finding.get('severity', 'Unknown')}",
            f"- **Confidence:** {finding.get('confidence', 'Not stated')}",
            f"- **Visible evidence:** {finding.get('description', '')}",
            f"- **Suggested follow-up:** {finding.get('recommendation', '')}",
            "",
        ])
    if not findings:
        lines.append("No localized findings were returned. Review the model summary and inspect the original image manually.")
    limitations = data.get("limitations", [])
    if limitations:
        lines += ["**Limitations:**"] + [f"- {x}" for x in limitations]
    lines += ["", "_AI-generated visual observations only. Verify findings on site with a qualified inspector._"]
    return {"report": "\n".join(lines), "findings": findings, "raw": raw}

def annotate_image(image_bytes, findings):
    image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    draw = ImageDraw.Draw(image)
    width, height = image.size
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", max(14, width // 65))
    except Exception:
        font = ImageFont.load_default()
    for idx, finding in enumerate(findings, 1):
        box = finding.get("bbox") if isinstance(finding, dict) else None
        if not isinstance(box, list) or len(box) != 4:
            continue
        try:
            x1, y1, x2, y2 = [float(v) for v in box]
            if max(abs(x1), abs(y1), abs(x2), abs(y2)) <= 1000:
                x1, x2 = x1 * width / 1000, x2 * width / 1000
                y1, y2 = y1 * height / 1000, y2 * height / 1000
            x1, x2 = sorted((max(0, min(width - 1, x1)), max(0, min(width - 1, x2))))
            y1, y2 = sorted((max(0, min(height - 1, y1)), max(0, min(height - 1, y2))))
            draw.rectangle((x1, y1, x2, y2), outline=(255, 90, 50), width=max(3, width // 400))
            label = f"{idx}. {finding.get('label', 'Possible finding')}"
            draw.text((x1, max(0, y1 - 24)), label, fill=(255, 255, 255), stroke_width=2, stroke_fill=(120, 20, 10), font=font)
        except (ValueError, TypeError):
            continue
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()

def transcribe_audio(audio_bytes, filename, language="Auto detect"):
    if len(audio_bytes) > 25 * 1024 * 1024:
        raise ValueError("Audio exceeds the 25 MB app upload limit.")
    client = get_client()
    model = get_secret("GROQ_STT_MODEL", DEFAULT_STT_MODEL)
    kwargs = {
        "file": (filename, audio_bytes),
        "model": model,
        "response_format": "text",
        "temperature": 0.0,
    }
    language_codes = {"English": "en", "Urdu": "ur", "Sindhi": "sd"}
    if language in language_codes:
        kwargs["language"] = language_codes[language]
    result = client.audio.transcriptions.create(**kwargs)
    return result if isinstance(result, str) else getattr(result, "text", str(result))

def _extract_video_frames(video_bytes, max_frames=4):
    suffix = ".mp4"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as temp:
        temp.write(video_bytes)
        path = temp.name
    capture = cv2.VideoCapture(path)
    frames = []
    try:
        total = int(capture.get(cv2.CAP_PROP_FRAME_COUNT))
        if total <= 0:
            raise RuntimeError("Could not read video frames. Try an MP4 encoded with H.264.")
        positions = np.linspace(0, max(total - 1, 0), min(max_frames, total), dtype=int)
        for position in positions:
            capture.set(cv2.CAP_PROP_POS_FRAMES, int(position))
            ok, frame = capture.read()
            if ok:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                image = Image.fromarray(frame)
                image.thumbnail((1100, 1100))
                buf = io.BytesIO()
                image.save(buf, format="JPEG", quality=85)
                frames.append((int(position), buf.getvalue(), image))
    finally:
        capture.release()
        Path(path).unlink(missing_ok=True)
    return frames

def analyze_video(video_bytes, filename, focus, max_frames=4):
    frames = _extract_video_frames(video_bytes, max_frames)
    reports, preview_frames = [], []
    for frame_number, image_bytes, preview in frames:
        result = analyze_image(
            image_bytes, f"{filename} · frame {frame_number}", focus
        )
        reports.append(f"### Frame {frame_number}\n{result['report']}")
        preview_frames.append(preview)
    full_report = (
        f"**Video:** {filename}\n\n"
        f"Analyzed {len(frames)} sampled frames. This is sampled-frame review, not continuous real-time tracking.\n\n"
        + "\n\n---\n\n".join(reports)
    )
    return {"report": full_report, "frames": preview_frames}

def reconstruct_sparse_3d(image_list):
    if len(image_list) < 2:
        raise ValueError("At least two overlapping images are required.")
    decoded = []
    for raw in image_list[:8]:
        image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_GRAYSCALE)
        if image is None:
            continue
        h, w = image.shape
        scale = min(1.0, 1400 / max(h, w))
        if scale < 1:
            image = cv2.resize(image, (int(w * scale), int(h * scale)))
            h, w = image.shape
        decoded.append((image, w, h))
    if len(decoded) < 2:
        raise ValueError("Could not decode at least two images.")
    img1, w1, h1 = decoded[0]
    img2, w2, h2 = decoded[1]
    if (w1, h1) != (w2, h2):
        img2 = cv2.resize(img2, (w1, h1))
    sift = cv2.SIFT_create(nfeatures=5000)
    kp1, des1 = sift.detectAndCompute(img1, None)
    kp2, des2 = sift.detectAndCompute(img2, None)
    if des1 is None or des2 is None:
        raise RuntimeError("Not enough visual features. Try textured photos with more overlap.")
    matcher = cv2.BFMatcher()
    pairs = matcher.knnMatch(des1, des2, k=2)
    good = [m for m, n in pairs if m.distance < 0.72 * n.distance]
    if len(good) < 12:
        raise RuntimeError(f"Only {len(good)} reliable feature matches. Try photos with 60–80% overlap.")
    p1 = np.float32([kp1[m.queryIdx].pt for m in good])
    p2 = np.float32([kp2[m.trainIdx].pt for m in good])
    focal = 1.2 * max(w1, h1)
    K = np.array([[focal, 0, w1 / 2], [0, focal, h1 / 2], [0, 0, 1]], dtype=np.float64)
    E, mask = cv2.findEssentialMat(p1, p2, K, method=cv2.RANSAC, prob=0.999, threshold=1.5)
    if E is None:
        raise RuntimeError("Could not estimate camera geometry. Check overlap and camera motion.")
    _, R, t, pose_mask = cv2.recoverPose(E, p1, p2, K, mask=mask)
    selected = pose_mask.ravel() > 0
    p1 = p1[selected]
    p2 = p2[selected]
    if len(p1) < 8:
        raise RuntimeError("Too few inlier matches for a stable sparse reconstruction.")
    P1 = K @ np.hstack((np.eye(3), np.zeros((3, 1))))
    P2 = K @ np.hstack((R, t))
    homogeneous = cv2.triangulatePoints(P1, P2, p1.T, p2.T)
    points = (homogeneous[:3] / homogeneous[3]).T
    valid = np.isfinite(points).all(axis=1) & (points[:, 2] > 0)
    points = points[valid]
    if len(points) < 8:
        raise RuntimeError("Triangulation produced too few usable 3D points.")
    points = points.astype(np.float32)
    ply_lines = ["ply", "format ascii 1.0", f"element vertex {len(points)}",
                 "property float x", "property float y", "property float z", "end_header"]
    ply_lines.extend(f"{x:.6f} {y:.6f} {z:.6f}" for x, y, z in points)
    summary = (
        f"Generated a sparse two-view point cloud with {len(points)} 3D points from "
        f"{len(good)} candidate feature matches. Scale and orientation are arbitrary because "
        "camera calibration and a known reference measurement were not supplied. "
        "This is not a watertight mesh or a dimensionally accurate survey model."
    )
    return {"points": points, "ply": ("\n".join(ply_lines)).encode("utf-8"), "summary": summary}

def build_pdf_report(title, modality, report_text):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=42, leftMargin=42, topMargin=48, bottomMargin=42)
    styles = getSampleStyleSheet()
    story = [
        Paragraph("InfraTwin AI", styles["Title"]),
        Paragraph("Infrastructure Inspection Record", styles["Heading2"]),
        Spacer(1, 10),
        Paragraph(f"<b>Record:</b> {title}", styles["BodyText"]),
        Paragraph(f"<b>Input type:</b> {modality}", styles["BodyText"]),
        Spacer(1, 14),
    ]
    for paragraph in report_text.split("\n"):
        line = paragraph.strip()
        if not line:
            story.append(Spacer(1, 5))
            continue
        safe = (line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
        safe = safe.replace("**", "")
        if safe.startswith("### "):
            story.append(Paragraph(safe[4:], styles["Heading3"]))
        elif safe.startswith("#### "):
            story.append(Paragraph(safe[5:], styles["Heading4"]))
        else:
            story.append(Paragraph(safe, styles["BodyText"]))
        story.append(Spacer(1, 4))
    story += [
        Spacer(1, 14),
        Paragraph(
            "<b>Disclaimer:</b> AI-generated observations are preliminary decision-support information. "
            "They are not a certified structural assessment. A qualified engineer must verify "
            "safety-critical findings on site.",
            styles["Italic"],
        ),
    ]
    doc.build(story)
    return buffer.getvalue()
