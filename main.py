import streamlit as st
import folium
from streamlit_folium import st_folium
from folium.plugins import Fullscreen
import geojson
from shapely.geometry import shape
from shapely.ops import unary_union
from pyproj import Transformer
from io import BytesIO
import json
from typing import List, Dict, Any, Tuple
import hashlib
from overture_buildings import (
    DEFAULT_FEATURE_LIMIT,
    fetch_buildings_from_overture,
)
from map_features import *

APP_TITLE = "Overture Buildings Explorer"
st.set_page_config(page_title=APP_TITLE, layout="wide")


@st.cache_data(show_spinner=False)
def compute_building_statistics(geojson_str: str) -> Dict[str, Any]:
    """
    Compute building statistics from GeoJSON data.
    Cached to avoid recomputing on every UI interaction.

    Args:
        geojson_str: JSON string of building data

    Returns:
        Dictionary containing computed statistics
    """
    data = json.loads(geojson_str)
    features = data.get('features', [])

    if not features:
        return {}

    heights = [f['properties'].get('height') for f in features if f['properties'].get('height')]
    floors = [f['properties'].get('num_floors') for f in features if f['properties'].get('num_floors')]
    classes = [f['properties'].get('class') for f in features if f['properties'].get('class')]

    sources = []
    for f in features:
        props = f['properties']
        if props.get('sources') and isinstance(props['sources'], list) and props['sources']:
            dataset = props['sources'][0].get('dataset', 'Unknown')
            sources.append(dataset)

    stats = {}

    if heights:
        stats['heights'] = {
            'count': len(heights),
            'avg': sum(heights) / len(heights),
            'min': min(heights),
            'max': max(heights)
        }

    if floors:
        stats['floors'] = {
            'count': len(floors),
            'avg': sum(floors) / len(floors),
            'min': min(floors),
            'max': max(floors)
        }

    if classes:
        class_counts = {}
        for c in classes:
            class_counts[c] = class_counts.get(c, 0) + 1
        stats['classes'] = {
            'total': len(classes),
            'counts': dict(sorted(class_counts.items(), key=lambda x: x[1], reverse=True)[:5])
        }

    if sources:
        source_counts = {}
        for s in sources:
            source_counts[s] = source_counts.get(s, 0) + 1
        stats['sources'] = dict(sorted(source_counts.items(), key=lambda x: x[1], reverse=True))

    return stats


@st.cache_data(show_spinner=False)
def get_paginated_features(geojson_str: str, page: int, features_per_page: int) -> Dict[str, Any]:
    """
    Get a paginated subset of features from GeoJSON data.

    Args:
        geojson_str: JSON string of building data
        page: Page number (0-indexed)
        features_per_page: Number of features per page

    Returns:
        GeoJSON FeatureCollection with paginated features
    """
    data = json.loads(geojson_str)
    all_features = data.get('features', [])

    start_idx = page * features_per_page
    end_idx = start_idx + features_per_page

    paginated_features = all_features[start_idx:end_idx]

    return {
        'type': 'FeatureCollection',
        'features': paginated_features
    }


def setup_app():
    # st.title(APP_TITLE)
    st.sidebar.title("Overture Buildings Explorer")

def initialize_session_state():
    for key, default in {
        'map_data': None,
        'filtered_building_data': None,
        'building_count': 0,
        'imagery_dates': [],
        'selected_feature_names': [],
        'info_box_visible': False,
        'lat': 0,
        'lon': 0,
        'input_geometry': None,
        'bounds': None,
        'zoom': 0,
        'data_truncated': False,
        'feature_limit': DEFAULT_FEATURE_LIMIT,
        'pagination_enabled': True,
        'features_per_page': 10000,
        'current_page': 0,
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default

def process_uploaded_file(uploaded_file):
    try:
        geojson_data = geojson.load(uploaded_file)
        features = geojson_data['features']
        feature_names = sorted([feature['properties'].get('name', f'Feature {i}') for i, feature in enumerate(features)])
        selected_feature_names = st.sidebar.multiselect(
            "Select features to display",
            feature_names,
            default=st.session_state.selected_feature_names if st.session_state.selected_feature_names else None
        )

        if st.session_state.selected_feature_names != selected_feature_names:
            st.session_state.filtered_building_data = None
            st.session_state.filtered_building_geojson = None
            st.session_state.building_count = 0
            st.session_state.info_box_visible = False
            st.session_state.data_truncated = False
            st.session_state.feature_limit = DEFAULT_FEATURE_LIMIT

        st.session_state.selected_feature_names = selected_feature_names

        if selected_feature_names:
            selected_features = [feature for feature in features if feature['properties'].get('name') in selected_feature_names]
            display_selected_features(selected_features)

    except Exception as e:
        st.sidebar.error(f"Error processing GeoJSON file: {str(e)}")
        st.sidebar.error("Please make sure your GeoJSON file is properly formatted.")

def display_selected_features(selected_features):
    geometries = [shape(feature['geometry']) for feature in selected_features]

    if len(geometries) == 1:
        input_geometry = geometries[0]
    else:
        input_geometry = unary_union(geometries)

    center_lat, center_lon = get_geometry_center(input_geometry)
    st.session_state.lat = center_lat
    st.session_state.lon = center_lon

    m = create_base_map(center_lat, center_lon)

    for feature in selected_features:
        folium.GeoJson(feature, style_function=lambda x: {
            'fillColor': '#3388ff',
            'color': '#3388ff',
            'weight': 2,
            'fillOpacity': 0.2
        }).add_to(m)

    Fullscreen(position="topright", title="Expand me", title_cancel="Exit me", force_separate_button=True).add_to(m)

    # Display buildings with pagination if enabled
    if st.session_state.filtered_building_data is not None:
        if st.session_state.pagination_enabled and hasattr(st.session_state, 'filtered_building_geojson'):
            # Get paginated data
            paginated_data = get_paginated_features(
                st.session_state.filtered_building_geojson,
                st.session_state.current_page,
                st.session_state.features_per_page
            )
            folium.GeoJson(paginated_data, style_function=lambda x: {
                'fillColor': '#ff7800',
                'color': '#ff7800',
                'weight': 1,
                'fillOpacity': 0.5
            }).add_to(m)
        else:
            folium.GeoJson(st.session_state.filtered_building_data).add_to(m)

    st.session_state.map_data = st_folium(m, width=1200, height=800)

    st.session_state.input_geometry = input_geometry

def get_geometry_center(geometry):
    if geometry.geom_type == 'Point':
        return geometry.y, geometry.x
    else:
        centroid = geometry.centroid
        return centroid.y, centroid.x

def create_base_map(lat, lon):
    m = folium.Map(location=[lat, lon], zoom_start=12)
    folium.TileLayer(
        name='ArcGIS World Imagery',
        control=True,
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='ArcGIS World Imagery'
    ).add_to(m)
    return m

def download_and_process_building_data(input_geometry):
    if input_geometry is None:
        st.sidebar.warning("Please select a feature before fetching building data.")
        return

    with st.sidebar.status("Fetching building data from Overture Maps...", expanded=True) as status:
        message_placeholder = st.empty()
        progress_bar = st.progress(0)
        info_placeholder = st.empty()

        def update_progress(message, progress):
            message_placeholder.write(message)
            progress_bar.progress(progress / 100.0)

            # Show cache hint on first request
            if progress == 0:
                info_placeholder.info("💡 Tip: Subsequent requests for the same area will be cached and load instantly!")

        try:
            # Check if data might be cached
            bounds = input_geometry.bounds
            bbox_tuple = (bounds[0], bounds[1], bounds[2], bounds[3])
            cache_key = hashlib.md5(f"{bbox_tuple[0]:.6f},{bbox_tuple[1]:.6f},{bbox_tuple[2]:.6f},{bbox_tuple[3]:.6f},{st.session_state.feature_limit}".encode()).hexdigest()

            info_placeholder.info(f"🔍 Checking cache (key: {cache_key[:8]}...)")

            result = fetch_buildings_from_overture(
                input_geometry,
                limit=st.session_state.feature_limit,
                progress_callback=update_progress
            )

            st.session_state.building_count = result.building_count
            st.session_state.filtered_building_data = result.geojson
            st.session_state.filtered_building_geojson = json.dumps(result.geojson, separators=(',', ':'))
            st.session_state.info_box_visible = True
            st.session_state.data_truncated = result.truncated
            st.session_state.feature_limit = result.limit
            st.session_state.current_page = 0  # Reset to first page

            info_placeholder.success(f"✅ Fetched {result.building_count} buildings")
            status.update(label="✓ Data fetched successfully!", state="complete", expanded=False)

        except Exception as e:
            progress_bar.empty()
            message_placeholder.empty()
            info_placeholder.empty()
            status.update(label="✗ Failed to fetch data", state="error", expanded=True)
            st.error("Unable to fetch building data from Overture Maps.")
            st.error(str(e))
            return

    st.rerun()

def display_fixed_info_box():
    with st.sidebar.expander("Building Data Summary", expanded=True):
        if st.session_state.selected_feature_names:
            num_features = len(st.session_state.selected_feature_names)
            if num_features == 1:
                st.metric(label="Location", value=st.session_state.selected_feature_names[0], label_visibility="hidden")
            else:
                st.metric(label="Selected Features", value=f"{num_features} features", label_visibility="hidden")
                st.write(", ".join(st.session_state.selected_feature_names))
        st.write(f"Lat/long: {st.session_state.lat:.6f}, {st.session_state.lon:.6f}")
        st.metric(label="Total buildings", value=f"{st.session_state.building_count}")

        if st.session_state.data_truncated:
            st.warning(
                "The number of buildings exceeds the display limit. Only the first "
                f"{st.session_state.feature_limit} features are shown."
            )

        # Pagination controls
        if st.session_state.building_count > 0:
            st.divider()
            st.subheader("Display Options")

            # Enable/disable pagination
            pagination_enabled = st.checkbox(
                "Enable pagination",
                value=st.session_state.pagination_enabled,
                help="When enabled, only a subset of buildings will be displayed on the map at once"
            )

            if pagination_enabled != st.session_state.pagination_enabled:
                st.session_state.pagination_enabled = pagination_enabled
                st.session_state.current_page = 0
                st.rerun()

            if pagination_enabled:
                # Features per page selector
                features_per_page = st.select_slider(
                    "Buildings per page",
                    options=[1000, 2500, 5000, 10000, 25000],
                    value=st.session_state.features_per_page,
                    help="Number of buildings to display on the map at once"
                )

                if features_per_page != st.session_state.features_per_page:
                    st.session_state.features_per_page = features_per_page
                    st.session_state.current_page = 0
                    st.rerun()

                # Calculate total pages
                total_pages = (st.session_state.building_count - 1) // st.session_state.features_per_page + 1

                if total_pages > 1:
                    st.write(f"Page {st.session_state.current_page + 1} of {total_pages}")

                    # Page navigation
                    col1, col2, col3 = st.columns(3)

                    with col1:
                        if st.button("◀ Prev", disabled=st.session_state.current_page == 0):
                            st.session_state.current_page -= 1
                            st.rerun()

                    with col2:
                        # Page number input
                        page_num = st.number_input(
                            "Go to page",
                            min_value=1,
                            max_value=total_pages,
                            value=st.session_state.current_page + 1,
                            step=1,
                            label_visibility="collapsed"
                        )
                        if page_num != st.session_state.current_page + 1:
                            st.session_state.current_page = page_num - 1
                            st.rerun()

                    with col3:
                        if st.button("Next ▶", disabled=st.session_state.current_page >= total_pages - 1):
                            st.session_state.current_page += 1
                            st.rerun()

                    # Show range of buildings being displayed
                    start_idx = st.session_state.current_page * st.session_state.features_per_page + 1
                    end_idx = min((st.session_state.current_page + 1) * st.session_state.features_per_page,
                                 st.session_state.building_count)
                    st.info(f"Showing buildings {start_idx}-{end_idx} of {st.session_state.building_count}")

        if hasattr(st.session_state, 'filtered_building_geojson') and st.session_state.filtered_building_geojson:
            st.divider()
            geojson_bytes = BytesIO(st.session_state.filtered_building_geojson.encode("utf-8"))
            st.download_button(
                label="📥 Download All Buildings (GeoJSON)",
                data=geojson_bytes,
                file_name="overture_buildings.geojson",
                mime="application/geo+json"
            )

    if st.session_state.filtered_building_data:
        display_building_attributes()


def display_building_attributes():
    """Display building attributes using cached statistics computation."""
    with st.sidebar.expander("Building Attributes Summary", expanded=False):
        if not hasattr(st.session_state, 'filtered_building_geojson'):
            return

        # Use cached computation
        stats = compute_building_statistics(st.session_state.filtered_building_geojson)

        if not stats:
            st.info("No attribute data available")
            return

        # Display height statistics
        if 'heights' in stats:
            h = stats['heights']
            st.write(f"🏢 **Height** ({h['count']} buildings)")
            st.write(f"   Avg: {h['avg']:.1f}m | Min: {h['min']:.1f}m | Max: {h['max']:.1f}m")

        # Display floor statistics
        if 'floors' in stats:
            f = stats['floors']
            st.write(f"📊 **Floors** ({f['count']} buildings)")
            st.write(f"   Avg: {f['avg']:.1f} | Min: {f['min']} | Max: {f['max']}")

        # Display building classes
        if 'classes' in stats:
            st.write(f"🏗️ **Building Classes** ({stats['classes']['total']} classified)")
            for cls, count in stats['classes']['counts'].items():
                st.write(f"   {cls}: {count}")

        # Display data sources
        if 'sources' in stats:
            st.write(f"📚 **Data Sources**")
            for src, count in stats['sources'].items():
                st.write(f"   {src}: {count} buildings")


def main():
    setup_app()

    uploaded_file = st.sidebar.file_uploader("Upload a GeoJSON file", type="geojson")
    initialize_session_state()

    if uploaded_file:
        process_uploaded_file(uploaded_file)

        if st.session_state.map_data is not None:
            bounds = st.session_state.map_data.get('bounds')
            zoom_level = st.session_state.map_data.get('zoom', 0)

            if zoom_level >= 12 and bounds:
                transformer = Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True)
                sw_x, sw_y = transformer.transform(bounds['_southWest']['lng'], bounds['_southWest']['lat'])
                ne_x, ne_y = transformer.transform(bounds['_northEast']['lng'], bounds['_northEast']['lat'])

                dates = get_imagery_dates((sw_x, sw_y, ne_x, ne_y), zoom_level)
                if dates:
                    dates = ", ".join(dates)
                    st.session_state.imagery_dates = dates
                    st.sidebar.write(f"Imagery dates: {dates}")
            elif zoom_level > 0:
                st.session_state.imagery_dates = f"Curent zoom level: {zoom_level} - Imagery dates are only available at zoom level 12 or higher."

        if st.sidebar.button("Fetch Overture Buildings", key="download_building_button"):
            download_and_process_building_data(st.session_state.input_geometry)
            
        if st.session_state.info_box_visible:
            display_fixed_info_box()
    
    # Display imagery dates below the map
    

if __name__ == "__main__":
    main()
