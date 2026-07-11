from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
import logging
from pydantic import BaseModel
import importlib
import pkgutil
from pathlib import Path

mcp = FastMCP(
    "pricing_model_mcp",
    host ="0.0.0.0",
    port=8001
)

MODEL_REGISTRY = {}
models_dir = Path(__file__).parent / "models"

for model_folder in models_dir.iterdir():
    if not model_folder.is_dir():
        continue
    model_name = model_folder.name
    for _, version_name, _ in pkgutil.iter_modules([str(model_folder)]):
        module = importlib.import_module(f"models.{model_name}.{version_name}")
        MODEL_REGISTRY[(model_name, version_name)] = module


@mcp.tool()
def get_model_metadata(model_name: str, version: str) -> dict:
    """
    Get the required inputs for a specific model version. Always call this
    BEFORE run_price_model for a model you haven't used yet — it returns
    exactly which fields are required and their types, so you can build
    a valid `inputs` dict.
    """
    module = MODEL_REGISTRY.get((model_name, version))
    if module is None:
        return {"error": f"No model '{model_name}' version '{version}' found."}
    return {"data": {
        "name": model_name,
        "version": version,
        "description": module.DESCRIPTION,
        "input_schema": module.Inputs.model_json_schema(),  # full JSON schema: fields, types, required, descriptions
    } }


@mcp.tool()
def run_price_model(model_name: str, version: str, inputs: dict) -> dict:
    """
    Run a specific model version. Requires calling get_model_metadata first
    if you don't already know this model's required inputs — passing an
    incomplete or malformed `inputs` dict returns a validation error listing
    exactly what's missing or wrong, rather than a computed price.
    """
    module = MODEL_REGISTRY.get((model_name, version))
    if module is None:
        raise ValueError(
            f"No model '{model_name}' version '{version}' found."
            )

    try:
        validated = module.Inputs(**inputs)
    except ValidationError as e:
        raise ValueError(
            f"Invalid inputs: {e.errors()}"
            ) from e

    price = module.run(validated)
    return {
        "price": price,
        "model": model_name,
        "version": version,
    }


@mcp.tool()
def list_price_models() -> dict:
    """
    List all available pricing models, their versions, and a short
    description of each. Use this to discover what's available before
    picking a model — call get_model_metadata on a specific model/version
    afterward to get its required inputs.
    """
    models: dict[str, list[dict]] = {}
    for (name, version), module in MODEL_REGISTRY.items():
        models.setdefault(name, []).append({
            "version": version,
            "description": module.DESCRIPTION,
        })
    return {
        "models": models
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8001)