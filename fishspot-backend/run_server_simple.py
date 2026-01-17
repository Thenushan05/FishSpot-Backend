"""
Simple uvicorn server runner without MongoDB dependencies for testing.
"""
import os
import uvicorn

if __name__ == "__main__":
    os.environ["ALLOW_ORIGINS"] = "*"
    os.environ["PYTHONPATH"] = "D:\\Fish-Full\\Backend\\fishspot-backend"
    
    # Try to run without MongoDB first
    try:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=8001,
            reload=False,
            log_level="info"
        )
    except Exception as e:
        print(f"❌ Server failed to start: {e}")
        print("💡 Try installing missing dependencies:")
        print("   pip install motor copernicusmarine")
        print("   or run: pip install -r requirements.txt")