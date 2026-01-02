"""
Aggregate OpenAPI specs from multiple microservices and serve them.

IMPORTANT: Service URLs must use the same public hostname to enable "Try it out"
functionality in Swagger UI/ReDoc.

Usage:
  # Start the docs server - use the public hostname, not localhost
  aggregate-openapi https://hostname/service1 https://hostname/service2

  # Start the docs server at a subpath (e.g., for /api-docs prefix)
  aggregate-openapi https://hostname/service1 https://hostname/service2 --path /api-docs

  # Generate Apache config (to stdout) and start server
  aggregate-openapi https://hostname/service1 https://hostname/service2 \
    --apache-config --hostname api-docs.example.com

  # Generate Apache config to file and start server
  aggregate-openapi https://hostname/service1 https://hostname/service2 \
    --path /api-docs --apache-config --hostname example.com --output api-docs.conf
"""

import argparse
import json
from pathlib import Path
from urllib.request import urlopen

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel

from stateless_microservice import models
from stateless_microservice.apache_conf import ApacheConfigParams, generate_apache_vhost_config, normalize_backend, sanitize_path


# Dynamically get all model names from stateless_microservice.models
SHARED_MODELS = {
    name for name in dir(models)
    if not name.startswith("_") and isinstance(getattr(models, name), type) and issubclass(getattr(models, name), BaseModel)
}


def fetch_openapi_spec(url: str) -> dict:
    """Fetch OpenAPI spec from a service URL."""
    url = f"{url.rstrip('/')}/openapi.json"
    with urlopen(url, timeout=10) as response:
        return json.loads(response.read())


def aggregate_specs(service_urls: list[str]) -> dict:
    """Fetch and merge OpenAPI specs from multiple services."""
    aggregated = {
        "openapi": "3.1.0",
        "info": {
            "title": "Aggregated Microservices API",
            "version": "1.0.0",
            "description": "API documentation for multiple microservices"
        },
        "paths": {},
        "components": {},
    }

    # OpenAPI 3.1.0 component types
    component_types = [
        "schemas",
        "responses",
        "parameters",
        "examples",
        "requestBodies",
        "headers",
        "securitySchemes",
        "links",
        "callbacks",
        "pathItems"
    ]

    # Initialize all component sections
    for component_type in component_types:
        aggregated["components"][component_type] = {}

    for url in service_urls:
        spec = fetch_openapi_spec(url)

        service_name = url.rstrip("/").split("/")[-1]
        service_title = spec.get("info", {}).get("title", service_name)

        print(f"  Loaded: {service_title}")

        # Merge paths with service name prefix
        for path, methods in spec.get("paths", {}).items():
            prefixed_path = f"/{service_name}{path}"
            aggregated["paths"][prefixed_path] = methods

        # Merge all component sections
        if "components" in spec:
            for component_type in component_types:
                if component_type not in spec["components"]:
                    continue

                for item_name, item_def in spec["components"][component_type].items():
                    if item_name in aggregated["components"][component_type]:
                        # Skip known shared models from stateless_microservice (schemas only)
                        if component_type == "schemas" and item_name in SHARED_MODELS:
                            continue
                        raise RuntimeError(
                            f"{component_type} naming conflict: '{item_name}' exists in multiple services"
                        )
                    aggregated["components"][component_type][item_name] = item_def

    return aggregated


def create_gateway_app(aggregated_spec: dict, root_path: str = "") -> FastAPI:
    """Create a FastAPI app that serves the aggregated OpenAPI spec."""
    app = FastAPI(
        title=aggregated_spec["info"]["title"],
        version=aggregated_spec["info"]["version"],
        description=aggregated_spec["info"]["description"],
        root_path=root_path,
    )

    # Override the openapi method to return our aggregated spec
    def custom_openapi():
        return aggregated_spec

    app.openapi = custom_openapi

    @app.get("/")
    async def root():
        return {
            "message": "Aggregated Microservices Gateway",
            "docs": f"{root_path}/docs",
            "redoc": f"{root_path}/redoc",
            "openapi": f"{root_path}/openapi.json"
        }

    return app


def main():
    parser = argparse.ArgumentParser(
        description="Aggregate OpenAPI specs from multiple microservices and serve them"
    )
    parser.add_argument(
        "urls",
        nargs="+",
        help="Service URLs (e.g., http://hostname/service1 http://hostname/service2)"
    )
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=8000,
        help="Port to serve on (default: 8000)"
    )

    # Apache config generation options
    apache_group = parser.add_argument_group("Apache config generation")
    apache_group.add_argument(
        "--apache-config",
        action="store_true",
        help="Generate Apache reverse-proxy config before starting server"
    )
    apache_group.add_argument(
        "--hostname",
        help="Public hostname for Apache config (e.g., api-docs.example.com)"
    )
    apache_group.add_argument(
        "--path",
        default="/",
        help="Public route path prefix for Apache config (default: /)"
    )
    apache_group.add_argument(
        "--https",
        action="store_true",
        help="Generate HTTPS config with SSL settings"
    )
    apache_group.add_argument(
        "--no-virtualhost",
        action="store_true",
        help="Emit only proxy directives without wrapping <VirtualHost>"
    )
    apache_group.add_argument(
        "--ssl-cert",
        help="Path to SSLCertificateFile when using --https"
    )
    apache_group.add_argument(
        "--ssl-key",
        help="Path to SSLCertificateKeyFile when using --https"
    )
    apache_group.add_argument(
        "--output",
        help="Write Apache config to this path. Use '-' for stdout (default: stdout)",
        default="-"
    )

    args = parser.parse_args()

    # If generating Apache config
    if args.apache_config:
        if not args.hostname:
            parser.error("--hostname is required when generating Apache config")

        backend_url, backend_path = normalize_backend(f"http://127.0.0.1:{args.port}")
        route_path = sanitize_path(args.path)

        params = ApacheConfigParams(
            service_name="api-docs",
            public_host=args.hostname,
            backend_url=backend_url,
            backend_path=backend_path,
            route_path=route_path,
            error_log="/var/log/apache2/api-docs-error.log",
            access_log="/var/log/apache2/api-docs-access.log",
            use_https=args.https,
            include_virtualhost=not args.no_virtualhost,
            ssl_certificate_file=args.ssl_cert,
            ssl_certificate_key_file=args.ssl_key,
        )

        config_text = generate_apache_vhost_config(params)

        if args.output == "-":
            print("\n" + "="*60)
            print("Apache Configuration:")
            print("="*60)
            print(config_text)
            print("="*60 + "\n")
        else:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(config_text + "\n")
            print(f"Wrote Apache config to {output_path}\n")

    aggregated = aggregate_specs(args.urls)

    print(f"\nAggregated {len(aggregated['paths'])} endpoints from {len(args.urls)} services")

    # Prepare root_path for FastAPI (remove trailing slash if present)
    root_path = args.path.rstrip("/") if args.path != "/" else ""

    # Serve with FastAPI
    app = create_gateway_app(aggregated, root_path=root_path)
    print(f"\nServing aggregated API docs at:")

    # Show public URLs if hostname is provided, otherwise show localhost
    if args.apache_config and args.hostname:
        protocol = "https" if args.https else "http"
        base_url = f"{protocol}://{args.hostname}{root_path}"
        print(f"   Swagger UI: {base_url}/docs")
        print(f"   ReDoc:      {base_url}/redoc")
        print(f"   OpenAPI:    {base_url}/openapi.json")
    else:
        print(f"   Swagger UI: http://localhost:{args.port}{root_path}/docs")
        print(f"   ReDoc:      http://localhost:{args.port}{root_path}/redoc")
        print(f"   OpenAPI:    http://localhost:{args.port}{root_path}/openapi.json")

    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
