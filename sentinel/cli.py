"""
Sentinel Gateway CLI
Commands:
  sentinel           — start the proxy gateway
  sentinel-dashboard — start the live terminal dashboard
"""
 
import click
import uvicorn
 
 
@click.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=8080, show_default=True)
@click.option("--reload", is_flag=True, default=False)
def sentinel(host, port, reload):
    """Start the Sentinel Gateway proxy."""
    click.echo(f"\n⬡ Sentinel Gateway starting on http://{host}:{port}\n")
    click.echo(f"  Set your AI tool's base URL:")
    click.echo(f"  export ANTHROPIC_BASE_URL=http://{host}:{port}/anthropic\n")
    uvicorn.run(
        "sentinel.gateway:app",
        host=host,
        port=port,
        reload=reload,
        log_level="warning",
    )
 
 
@click.command()
def dashboard():
    """Start the live terminal dashboard."""
    from sentinel.dashboard import run
    run()