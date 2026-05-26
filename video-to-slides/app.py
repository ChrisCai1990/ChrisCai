import os
import uuid
import json
import zipfile
import io
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template
import cv2
import numpy as np
from PIL import Image
from skimage.metrics import structural_similarity as ssim
from reportlab.lib.pagesizes import landscape, A4
from reportlab.platypus import Image as RLImage
from reportlab.lib.units import mm

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB limit
UPLOAD_FOLDER = Path('/tmp/video_slides')
UPLOAD_FOLDER.mkdir(exist_ok=True)


def extract_slides(video_path: str, ssim_threshold: float = 0.92, min_interval_sec: float = 0.5) -> list[np.ndarray]:
    """
    Extract unique slides from a video using SSIM-based scene detection.
    Returns list of BGR frames representing each unique slide.
    """
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise ValueError("Cannot open video file")

    fps = cap.get(cv2.CAP_PROP_FPS)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    min_frame_gap = max(1, int(fps * min_interval_sec))

    slides = []
    prev_gray = None
    last_captured_frame_idx = -min_frame_gap
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.resize(gray, (320, 240))  # downsample for speed

        if prev_gray is None:
            slides.append(frame.copy())
            prev_gray = gray
            last_captured_frame_idx = frame_idx
            frame_idx += 1
            continue

        # Skip frames within min_interval to avoid duplicate detection
        if frame_idx - last_captured_frame_idx < min_frame_gap:
            frame_idx += 1
            continue

        score, _ = ssim(prev_gray, gray, full=True)

        if score < ssim_threshold:
            # New slide detected — wait a bit then capture to skip transition frames
            stable_idx = frame_idx + max(1, int(fps * 0.3))
            cap.set(cv2.CAP_PROP_POS_FRAMES, stable_idx)
            ret2, stable_frame = cap.read()
            if ret2:
                slides.append(stable_frame.copy())
                stable_gray = cv2.cvtColor(stable_frame, cv2.COLOR_BGR2GRAY)
                prev_gray = cv2.resize(stable_gray, (320, 240))
                last_captured_frame_idx = stable_idx
                frame_idx = stable_idx + 1
            else:
                slides.append(frame.copy())
                prev_gray = gray
                last_captured_frame_idx = frame_idx
                frame_idx += 1
        else:
            prev_gray = gray
            frame_idx += 1

    cap.release()
    return slides


def deduplicate_slides(slides: list[np.ndarray], threshold: float = 0.97) -> list[np.ndarray]:
    """Remove near-duplicate slides using pairwise SSIM on consecutive frames."""
    if not slides:
        return slides

    unique = [slides[0]]
    for frame in slides[1:]:
        prev = cv2.resize(cv2.cvtColor(unique[-1], cv2.COLOR_BGR2GRAY), (320, 240))
        curr = cv2.resize(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), (320, 240))
        score, _ = ssim(prev, curr, full=True)
        if score < threshold:
            unique.append(frame)

    return unique


def frames_to_pdf(frames: list[np.ndarray], output_path: str):
    """Combine frames into a single PDF using canvas, one frame per page."""
    from reportlab.pdfgen import canvas as pdfcanvas
    from reportlab.lib.utils import ImageReader

    page_w, page_h = landscape(A4)
    margin = 10 * mm
    avail_w = page_w - 2 * margin
    avail_h = page_h - 2 * margin

    c = pdfcanvas.Canvas(output_path, pagesize=landscape(A4))
    for frame in frames:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        ih, iw = frame.shape[:2]
        scale = min(avail_w / iw, avail_h / ih)
        draw_w = iw * scale
        draw_h = ih * scale
        x = (page_w - draw_w) / 2
        y = (page_h - draw_h) / 2

        c.drawImage(ImageReader(pil_img), x, y, width=draw_w, height=draw_h)
        c.showPage()

    c.save()


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/extract', methods=['POST'])
def extract():
    if 'video' not in request.files:
        return jsonify({'error': 'No video file uploaded'}), 400

    file = request.files['video']
    if not file.filename:
        return jsonify({'error': 'Empty filename'}), 400

    ssim_threshold = float(request.form.get('threshold', 0.92))
    export_format = request.form.get('format', 'png')  # 'png', 'pdf', 'zip'

    session_id = uuid.uuid4().hex
    session_dir = UPLOAD_FOLDER / session_id
    session_dir.mkdir()

    video_path = session_dir / 'input.mp4'
    file.save(str(video_path))

    try:
        slides = extract_slides(str(video_path), ssim_threshold=ssim_threshold)
        slides = deduplicate_slides(slides)

        if not slides:
            return jsonify({'error': 'No slides detected in video'}), 400

        if export_format == 'pdf':
            pdf_path = session_dir / 'slides.pdf'
            frames_to_pdf(slides, str(pdf_path))
            return send_file(str(pdf_path), as_attachment=True, download_name='slides.pdf', mimetype='application/pdf')

        # Export as ZIP of PNGs
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, frame in enumerate(slides):
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                pil_img = Image.fromarray(rgb)
                img_buf = io.BytesIO()
                pil_img.save(img_buf, format='PNG')
                img_buf.seek(0)
                zf.writestr(f'slide_{i+1:03d}.png', img_buf.read())

        zip_buf.seek(0)
        return send_file(
            zip_buf,
            as_attachment=True,
            download_name='slides.zip',
            mimetype='application/zip'
        )

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        # Cleanup uploaded video to save space
        if video_path.exists():
            video_path.unlink()


@app.route('/preview', methods=['POST'])
def preview():
    """Return slide count and thumbnail previews for the uploaded video."""
    if 'video' not in request.files:
        return jsonify({'error': 'No video file uploaded'}), 400

    file = request.files['video']
    ssim_threshold = float(request.form.get('threshold', 0.92))

    session_id = uuid.uuid4().hex
    session_dir = UPLOAD_FOLDER / session_id
    session_dir.mkdir()

    video_path = session_dir / 'input.mp4'
    file.save(str(video_path))

    try:
        slides = extract_slides(str(video_path), ssim_threshold=ssim_threshold)
        slides = deduplicate_slides(slides)

        # Save thumbnails
        thumbs = []
        for i, frame in enumerate(slides):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            pil_img.thumbnail((400, 300))
            thumb_path = session_dir / f'thumb_{i}.jpg'
            pil_img.save(str(thumb_path), format='JPEG', quality=80)
            thumbs.append(f'/thumb/{session_id}/{i}')

        return jsonify({'count': len(slides), 'session_id': session_id, 'thumbnails': thumbs})

    except Exception as e:
        return jsonify({'error': str(e)}), 500

    finally:
        if video_path.exists():
            video_path.unlink()


@app.route('/thumb/<session_id>/<int:idx>')
def thumbnail(session_id, idx):
    thumb_path = UPLOAD_FOLDER / session_id / f'thumb_{idx}.jpg'
    if not thumb_path.exists():
        return 'Not found', 404
    return send_file(str(thumb_path), mimetype='image/jpeg')


@app.route('/download/<session_id>/<fmt>')
def download(session_id, fmt):
    session_dir = UPLOAD_FOLDER / session_id
    if not session_dir.exists():
        return 'Session expired', 404

    thumbs = sorted(session_dir.glob('thumb_*.jpg'))
    frames = []
    for t in thumbs:
        pil = Image.open(str(t)).convert('RGB')
        frames.append(cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR))

    if fmt == 'pdf':
        pdf_path = session_dir / 'slides.pdf'
        frames_to_pdf(frames, str(pdf_path))
        return send_file(str(pdf_path), as_attachment=True, download_name='slides.pdf', mimetype='application/pdf')

    zip_buf = io.BytesIO()
    with zipfile.ZipFile(zip_buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        for i, frame in enumerate(frames):
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pil_img = Image.fromarray(rgb)
            img_buf = io.BytesIO()
            pil_img.save(img_buf, format='PNG')
            img_buf.seek(0)
            zf.writestr(f'slide_{i+1:03d}.png', img_buf.read())
    zip_buf.seek(0)
    return send_file(zip_buf, as_attachment=True, download_name='slides.zip', mimetype='application/zip')


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)
