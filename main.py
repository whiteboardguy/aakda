from app.cfg import settings

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.aakda:app", host=f"{settings.aakda_host}", port=settings.aakda_port, reload=settings.DEBUG)
