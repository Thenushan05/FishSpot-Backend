"""
Simple uvicorn server runner to keep server alive and test CORS.
"""
import sys, os
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import warnings
# Suppress sklearn version mismatch warnings from the saved model (harmless)
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")
warnings.filterwarnings("ignore", category=UserWarning, module="xgboost")
import uvicorn

if __name__ == "__main__":
    os.environ["ALLOW_ORIGINS"] = "*"
    os.environ["PYTHONPATH"] = "D:\\Fish-Full\\Backend\\fishspot-backend"
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=False,
        log_level="info"
    )
