"""
Simple uvicorn server runner to keep server alive and test CORS.
"""
import os
import uvicorn

if __name__ == "__main__":
    os.environ["ALLOW_ORIGINS"] = "*"
    os.environ["PYTHONPATH"] = "D:\\Fish-Full\\Backend\\fishspot-backend"
    
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8001,
        reload=False,
        log_level="info"
    )
