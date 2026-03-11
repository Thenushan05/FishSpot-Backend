"""Quick inference test for /api/v1/vision/identify"""
import urllib.request, json
from PIL import Image
import io

# Create a synthetic 640x480 blue test image
img = Image.new("RGB", (640, 480), color=(30, 100, 180))
buf = io.BytesIO()
img.save(buf, "JPEG")
img_bytes = buf.getvalue()

# Multipart POST
body = (
    b"------boundary123\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.jpg\"\r\n"
    b"Content-Type: image/jpeg\r\n\r\n" + img_bytes + b"\r\n------boundary123--\r\n"
)
req = urllib.request.Request(
    "http://localhost:8000/api/v1/vision/identify",
    data=body,
    headers={"Content-Type": "multipart/form-data; boundary=----boundary123"},
)
with urllib.request.urlopen(req, timeout=15) as r:
    result = json.loads(r.read())

print("Model:            ", result["model"])
print("Inference:        ", result["inference_ms"], "ms")
print("Image size:       ", result["image_size"])
print("Total detections: ", result["total_detections"])
if result["primary"]:
    p = result["primary"]
    print("Primary class:    ", p["class_name"])
    print("Confidence:       ", p["confidence_pct"], "%")
    print("Market code:      ", p["market_code"])
else:
    print("No fish detected (expected for plain image)")
print()
print("Status: OK — inference pipeline working")
