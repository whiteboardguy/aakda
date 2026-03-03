from app.cfg import settings

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.aakda:app",
        host=settings.aakda_host,
        port=settings.aakda_port,
        reload=settings.DEBUG and settings.opts_workers == 1,
        workers=settings.opts_workers if not settings.DEBUG else None,
    )
