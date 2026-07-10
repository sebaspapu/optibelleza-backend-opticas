from fastapi.middleware.cors import CORSMiddleware

def setup_cors(app):
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  #  ruta del frontend
            "http://localhost:5174",  #  ruta alternativa del frontend
            "http://localhost:3000",  
            "http://127.0.0.1:5174",
            "http://127.0.0.1:5173",  
            "http://127.0.0.1:3000", 
            "https://optibelleza-frontend.vercel.app",
        ],  
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )