# InfraTwin AI

AI-assisted infrastructure inspection workspace for image, audio and video evidence, experimental 3D reconstruction, inspection records and PDF reports.

## Features included

- Groq-powered engineering assistant (GPT-OSS 120B by default)
- Vision-based photo review using a Groq vision model
- AI-suggested approximate image regions and annotated-image export
- Multilingual speech transcription using Groq Whisper
- Video sampling and frame-by-frame visual review
- Experimental two-view sparse 3D point-cloud reconstruction from overlapping photos
- Interactive 3D point-cloud viewer and PLY export
- PDF inspection reports
- Inspection workspace and analysis history
- Optional persistent Supabase database; SQLite fallback for quick testing

## Important engineering limitations

This is a portfolio/research prototype, not certified inspection software.

- Vision model outputs are preliminary observations, not trained defect-detector measurements or confirmed diagnoses.
- AI-suggested bounding boxes are approximate and must be checked against the original image.
- Video analysis samples a limited number of frames; it is not continuous tracking.
- The 3D module currently produces an experimental sparse two-view point cloud, not a dense textured mesh or a calibrated survey model. It needs overlapping photographs with good texture and viewpoint change. Scale and orientation are arbitrary without camera calibration and a known reference dimension.
- Never use AI output alone to decide whether a structure is safe.

## GitHub structure

```text
InfraTwin_AI/
├── app.py
├── backend.py
├── database.py
├── requirements.txt
├── README.md
└── .streamlit/
    └── config.toml
```

## Deploy on Streamlit Community Cloud

1. Create a GitHub repository named `InfraTwin_AI`.
2. Upload the files and the `.streamlit/config.toml` file.
3. Open https://share.streamlit.io/ and connect GitHub.
4. Select this repository and set the main file to `app.py`.
5. Open the app's Advanced settings / Secrets and add:

```toml
GROQ_API_KEY = "your_groq_api_key"
GROQ_TEXT_MODEL = "openai/gpt-oss-120b"
GROQ_VISION_MODEL = "qwen/qwen3.8-27b"
GROQ_STT_MODEL = "whisper-large-v3-turbo"
```

6. Deploy.

Check your Groq Console for model access and quotas. Model availability and pricing can change. The vision model is configured separately because the GPT-OSS text model is not the image-analysis model.

## Optional persistent database (recommended)

For durable records on Streamlit Community Cloud, create a Supabase project and add these tables in the Supabase SQL Editor:

```sql
create table if not exists projects (
  id text primary key,
  title text not null,
  created_at timestamptz not null
);

create table if not exists messages (
  id text primary key,
  project_id text not null references projects(id),
  role text not null,
  content text not null,
  created_at timestamptz not null
);

create table if not exists inspections (
  id text primary key,
  title text not null,
  modality text not null,
  result text not null,
  created_at timestamptz not null
);
```

Then add the following to Streamlit Secrets:

```toml
SUPABASE_URL = "https://YOUR_PROJECT.supabase.co"
SUPABASE_KEY = "your_supabase_anon_or_publishable_key"
```

For a public app, configure Supabase Row Level Security and user authentication before storing private inspection data. Do not expose a service-role key in a public app.

Without Supabase credentials, the app uses a local SQLite database. Streamlit Community Cloud does not guarantee local file persistence, so SQLite should be treated as temporary demo storage there.

## Upload and resource limits

The app limits audio to 25 MB and video to 80 MB. Large video processing and 3D reconstruction may exceed Streamlit Community Cloud resource limits. For heavier or production use, move those jobs to a separate worker/container and keep Streamlit as the user interface.

## Local development

Install dependencies from `requirements.txt`, then run:

```bash
streamlit run app.py
```

Create `.streamlit/secrets.toml` locally (do not commit it) with the same Groq keys shown above.

## License

Add a license after deciding how you want others to reuse the project.
