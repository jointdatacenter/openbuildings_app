"""Utility functions for working with the Google Open Buildings dataset via Earth Engine."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Dict

import ee
from shapely.geometry import shape as shapely_shape, mapping


DATASET_ID = "GOOGLE/Research/open-buildings/v3/polygons"
DEFAULT_FEATURE_LIMIT = 5000

_ee_initialized = False


class EarthEngineInitializationError(RuntimeError):
    """Raised when the Earth Engine client cannot be initialised."""


@dataclass
class BuildingFetchResult:
    """Container for the results returned from Earth Engine."""

    geojson: Dict[str, Any]
    building_count: int
    avg_confidence: float
    truncated: bool
    limit: int


def _build_service_account_credentials(service_account: str, private_key: str | None, key_path: str | None):
    """Create service account credentials using either raw key data or a file path."""

    private_key_data = None
    if private_key:
        # Support newline-delimited JSON stored in environment variables.
        private_key_data = private_key.replace("\\n", "\n")

    if private_key_data is not None:
        return ee.ServiceAccountCredentials(service_account, key_data=private_key_data)

    if key_path:
        return ee.ServiceAccountCredentials(service_account, key_path)

    raise EarthEngineInitializationError(
        "EE_SERVICE_ACCOUNT is set but neither EE_PRIVATE_KEY nor EE_CREDENTIALS_PATH were provided."
    )


def is_authenticated() -> bool:
    """Check if Earth Engine credentials exist."""
    credentials_path = os.path.expanduser("~/.config/earthengine/credentials")
    return os.path.exists(credentials_path)


def clear_credentials() -> None:
    """Remove saved Earth Engine credentials."""
    global _ee_initialized
    _ee_initialized = False
    credentials_path = os.path.expanduser("~/.config/earthengine/credentials")
    if os.path.exists(credentials_path):
        os.remove(credentials_path)


def authenticate_earth_engine(project_id: str | None = None) -> None:
    """Trigger the Earth Engine authentication flow."""
    ee.Authenticate(force=True)


def initialize_earth_engine(project_id: str | None = None) -> None:
    """Initialise the Earth Engine client if it has not already been initialised."""

    global _ee_initialized

    if _ee_initialized:
        return

    service_account = os.getenv("EE_SERVICE_ACCOUNT")
    private_key = os.getenv("EE_PRIVATE_KEY")
    key_path = os.getenv("EE_CREDENTIALS_PATH")
    ee_project = project_id or os.getenv("EE_PROJECT")

    try:
        if service_account:
            credentials = _build_service_account_credentials(service_account, private_key, key_path)
            ee.Initialize(credentials, project=ee_project)
        else:
            if ee_project:
                ee.Initialize(project=ee_project)
            else:
                ee.Initialize()
        _ee_initialized = True
    except Exception as exc:
        _ee_initialized = False
        raise EarthEngineInitializationError(
            "Failed to initialise Google Earth Engine. Provide EE_PROJECT environment variable "
            "or EE_SERVICE_ACCOUNT and EE_PRIVATE_KEY environment variables."
        ) from exc


def _to_feature_collection_dict(feature_collection: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise a GeoJSON dictionary returned by Earth Engine."""

    features = []
    for feature in feature_collection.get("features", []):
        geometry = feature.get("geometry")
        properties = feature.get("properties", {})

        if not geometry:
            continue

        # Compute centroid coordinates so we can mimic the metadata provided by the CSV download flow.
        centroid = shapely_shape(geometry).centroid
        feature_properties = {
            "latitude": centroid.y,
            "longitude": centroid.x,
            "area_in_meters": properties.get("area"),
            "confidence": properties.get("confidence"),
            "full_plus_code": properties.get("plus_code"),
        }

        features.append({
            "type": "Feature",
            "geometry": geometry,
            "properties": feature_properties,
        })

    return {
        "type": "FeatureCollection",
        "features": features,
    }


def fetch_buildings_from_gee(input_geometry, limit: int = DEFAULT_FEATURE_LIMIT) -> BuildingFetchResult:
    """Fetch building footprints from Google Earth Engine for the provided geometry."""

    initialize_earth_engine()

    ee_geometry = ee.Geometry(mapping(input_geometry))
    feature_collection = ee.FeatureCollection(DATASET_ID).filter(
        ee.Filter.intersects(".geo", ee_geometry, maxError=10)
    )

    building_count = int(feature_collection.size().getInfo())
    avg_confidence = feature_collection.aggregate_mean("confidence").getInfo() or 0.0

    limited_collection = feature_collection.limit(limit)
    geojson_dict = limited_collection.getInfo()
    geojson = _to_feature_collection_dict(geojson_dict)

    return BuildingFetchResult(
        geojson=geojson,
        building_count=building_count,
        avg_confidence=float(avg_confidence),
        truncated=building_count > limit,
        limit=limit,
    )
