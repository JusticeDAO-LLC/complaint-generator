from fastapi import APIRouter, FastAPI


def attach_router_routes(app: FastAPI, router: APIRouter) -> FastAPI:
    """Attach router routes while keeping app.routes inspectable across FastAPI versions."""
    app.include_router(router)
    included_router = app.routes[-1] if app.routes else None
    if getattr(included_router, "path", None) is not None:
        return app
    for route in router.routes:
        if route not in app.router.routes:
            app.router.routes.append(route)
    try:
        if included_router in app.router.routes:
            app.router.routes.remove(included_router)
    except ValueError:
        pass
    return app
