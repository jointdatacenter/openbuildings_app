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
from overture_buildings import (
    DEFAULT_FEATURE_LIMIT,
    OVERTURE_RELEASE,
    fetch_buildings_from_overture,
)
from map_features import *

APP_TITLE = "Overture Buildings Explorer"
st.set_page_config(page_title=APP_TITLE, layout="wide")

# Remove default Streamlit padding and margins
st.markdown("""
    <style>
        .main .block-container {
            padding-top: 1rem;
            padding-right: 0rem !important;
            padding-left: 1rem;
            padding-bottom: 0rem;
            max-width: 100% !important;
        }
        .main {
            padding-right: 0rem !important;
        }
        section.main > div {
            padding-right: 0rem !important;
        }
        iframe {
            width: 100% !important;
        }
        div[data-testid="stVerticalBlock"] > div {
            padding-right: 0rem !important;
        }
    </style>
""", unsafe_allow_html=True)


# ============================================================================
# SESSION STATE MANAGEMENT
# ============================================================================

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
        'feature_limit': 1000000,
        'building_opacity': 0.6,
        'last_selected_features': [],
        'current_selected_features': None,
    }.items():
        if key not in st.session_state:
            st.session_state[key] = default


def reset_building_data():
    st.session_state.filtered_building_data = None
    st.session_state.filtered_building_geojson = None
    st.session_state.building_count = 0
    st.session_state.info_box_visible = False
    st.session_state.data_truncated = False
    st.session_state.feature_limit = DEFAULT_FEATURE_LIMIT


# ============================================================================
# GEOMETRY UTILITIES
# ============================================================================

def get_geometry_center(geometry):
    if geometry.geom_type == 'Point':
        return geometry.y, geometry.x
    else:
        centroid = geometry.centroid
        return centroid.y, centroid.x


def create_unified_geometry(selected_features):
    geometries = [shape(feature['geometry']) for feature in selected_features]
    if len(geometries) == 1:
        return geometries[0]
    else:
        return unary_union(geometries)


# ============================================================================
# MAP CREATION
# ============================================================================

def create_base_map(lat, lon):
    m = folium.Map(location=[lat, lon], zoom_start=12)
    folium.TileLayer(
        name='ArcGIS World Imagery',
        control=True,
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='ArcGIS World Imagery'
    ).add_to(m)
    return m


def add_selected_features_to_map(m, selected_features):
    for feature in selected_features:
        folium.GeoJson(feature, style_function=lambda x: {
            'fillColor': '#3388ff',
            'color': '#3388ff',
            'weight': 2,
            'fillOpacity': 0.2
        }).add_to(m)


def add_building_footprints_to_map(m, building_data, opacity):
    folium.GeoJson(
        building_data,
        style_function=lambda x: {
            'fillColor': '#ff7800',
            'color': '#ff7800',
            'weight': 1,
            'fillOpacity': opacity * 0.4,
            'opacity': opacity
        }
    ).add_to(m)


def create_map_with_features(selected_features):
    input_geometry = create_unified_geometry(selected_features)

    center_lat, center_lon = get_geometry_center(input_geometry)
    st.session_state.lat = center_lat
    st.session_state.lon = center_lon
    st.session_state.input_geometry = input_geometry

    m = create_base_map(center_lat, center_lon)
    add_selected_features_to_map(m, selected_features)

    Fullscreen(position="topright", title="Expand me", title_cancel="Exit me", force_separate_button=True).add_to(m)

    if st.session_state.filtered_building_data is not None:
        add_building_footprints_to_map(m, st.session_state.filtered_building_data, st.session_state.building_opacity)

    return m


def render_map(selected_features):
    m = create_map_with_features(selected_features)
    st.session_state.map_data = st_folium(m, width=None, height=800, use_container_width=True)


# ============================================================================
# METADATA CALCULATION
# ============================================================================

def calculate_metadata_stats(features):
    total_buildings = len(features)

    heights = [f['properties'].get('height') for f in features if f['properties'].get('height')]
    floors = [f['properties'].get('num_floors') for f in features if f['properties'].get('num_floors')]
    classes = [f['properties'].get('class') for f in features if f['properties'].get('class')]

    sources = []
    for f in features:
        props = f['properties']
        if props.get('sources') and isinstance(props['sources'], list) and props['sources']:
            dataset = props['sources'][0].get('dataset', 'Unknown')
            sources.append(dataset)

    return {
        'total_buildings': total_buildings,
        'heights': heights,
        'floors': floors,
        'classes': classes,
        'sources': sources
    }


# ============================================================================
# UI COMPONENTS - METADATA DISPLAY
# ============================================================================

def display_height_metadata(heights, total_buildings):
    height_coverage = (len(heights) / total_buildings * 100) if total_buildings > 0 else 0
    if heights:
        avg_height = sum(heights) / len(heights)
        min_height = min(heights)
        max_height = max(heights)
        st.write(f"🏢 **Height** - {height_coverage:.1f}% coverage")
        st.write(f"   Avg: {avg_height:.1f}m | Min: {min_height:.1f}m | Max: {max_height:.1f}m")
    else:
        st.write(f"🏢 **Height** - 0% coverage")


def display_floors_metadata(floors, total_buildings):
    floors_coverage = (len(floors) / total_buildings * 100) if total_buildings > 0 else 0
    if floors:
        st.write(f"📊 **Floors** - {floors_coverage:.1f}% coverage")
    else:
        st.write(f"📊 **Floors** - 0% coverage")


def display_classes_metadata(classes, total_buildings):
    class_coverage = (len(classes) / total_buildings * 100) if total_buildings > 0 else 0
    st.write(f"🏗️ **Building Classes** - {class_coverage:.1f}% coverage")


def display_sources_metadata(sources, total_buildings):
    if sources:
        source_counts = {}
        for s in sources:
            source_counts[s] = source_counts.get(s, 0) + 1
        st.write(f"**Data Sources**")
        for src, count in sorted(source_counts.items(), key=lambda x: x[1], reverse=True):
            percentage = (count / total_buildings * 100)
            st.write(f"   • **{src}**: {percentage:.1f}%")


def display_metadata_summary(features):
    #st.markdown("---")
    #st.markdown("**Metadata Coverage**")

    stats = calculate_metadata_stats(features)

    display_height_metadata(stats['heights'], stats['total_buildings'])
    display_floors_metadata(stats['floors'], stats['total_buildings'])
    display_classes_metadata(stats['classes'], stats['total_buildings'])
    display_sources_metadata(stats['sources'], stats['total_buildings'])


# ============================================================================
# UI COMPONENTS - SIDEBAR
# ============================================================================

def display_location_info():
    if st.session_state.selected_feature_names:
        num_features = len(st.session_state.selected_feature_names)
        if num_features == 1:
            st.metric(label="Location", value=st.session_state.selected_feature_names[0], label_visibility="hidden")
        else:
            st.metric(label="Selected Features", value=f"{num_features} features", label_visibility="hidden")
            st.write(", ".join(st.session_state.selected_feature_names))
    st.write(f"Lat/long: {st.session_state.lat:.6f}, {st.session_state.lon:.6f}")


def display_building_summary():
    with st.sidebar.expander("Building Data Summary", expanded=True):
        display_location_info()
        st.metric(label="Total buildings", value=f"{st.session_state.building_count}")

        if st.session_state.data_truncated:
            st.warning(
                "The number of buildings exceeds the display limit. Only the first "
                f"{st.session_state.feature_limit} features are shown."
            )

        if st.session_state.filtered_building_data:
            features = st.session_state.filtered_building_data['features']
            if features:
                display_metadata_summary(features)

        if hasattr(st.session_state, 'filtered_building_geojson') and st.session_state.filtered_building_geojson:
            geojson_bytes = BytesIO(st.session_state.filtered_building_geojson.encode("utf-8"))
            st.download_button(
                label="Download GeoJSON",
                data=geojson_bytes,
                file_name="overture_buildings.geojson",
                mime="application/geo+json"
            )


def render_opacity_slider():
    if st.session_state.filtered_building_data is not None:
        st.session_state.building_opacity = st.sidebar.slider(
            "Building Footprint Opacity",
            min_value=0.0,
            max_value=1.0,
            value=st.session_state.building_opacity,
            step=0.1,
            help="Adjust opacity to see satellite imagery below buildings",
            key="opacity_slider"
        )


# ============================================================================
# FILE UPLOAD AND PROCESSING
# ============================================================================

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
            reset_building_data()

        st.session_state.selected_feature_names = selected_feature_names

        if selected_feature_names:
            selected_features = [feature for feature in features if feature['properties'].get('name') in selected_feature_names]
            st.session_state.current_selected_features = selected_features

            if st.session_state.last_selected_features != selected_feature_names or st.session_state.input_geometry is None:
                st.session_state.last_selected_features = selected_feature_names.copy()

    except Exception as e:
        st.sidebar.error(f"Error processing GeoJSON file: {str(e)}")
        st.sidebar.error("Please make sure your GeoJSON file is properly formatted.")


# ============================================================================
# BUILDING DATA FETCHING
# ============================================================================

def download_and_process_building_data(input_geometry):
    if input_geometry is None:
        st.sidebar.warning("Please select a feature before fetching building data.")
        return

    with st.sidebar.status("Loading...", expanded=True) as status:
        message_placeholder = st.empty()
        progress_bar = st.progress(0)

        def update_progress(message, progress):
            message_placeholder.write(message)
            progress_bar.progress(progress)

        try:
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

            status.update(label="✓ Data fetched successfully!", state="complete", expanded=False)

        except Exception as e:
            progress_bar.empty()
            message_placeholder.empty()
            status.update(label="✗ Failed to fetch data", state="error", expanded=True)
            st.error("Unable to fetch building data from Overture Maps.")
            st.error(str(e))
            return

    st.rerun()


# ============================================================================
# IMAGERY DATE HANDLING
# ============================================================================

def process_imagery_dates(bounds, zoom_level):
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


# ============================================================================
# MAIN APPLICATION
# ============================================================================

def main():
    st.sidebar.title("Overture Buildings Explorer")
    st.sidebar.caption(f"Data Release: {OVERTURE_RELEASE}")
    initialize_session_state()

    uploaded_file = st.sidebar.file_uploader("Upload a GeoJSON file", type="geojson")

    if uploaded_file:
        process_uploaded_file(uploaded_file)

        if st.session_state.current_selected_features is not None:
            render_map(st.session_state.current_selected_features)

        if st.session_state.map_data is not None:
            bounds = st.session_state.map_data.get('bounds')
            zoom_level = st.session_state.map_data.get('zoom', 0)
            process_imagery_dates(bounds, zoom_level)

        if st.sidebar.button("Fetch Overture Buildings", key="download_building_button"):
            download_and_process_building_data(st.session_state.input_geometry)

        render_opacity_slider()

        if st.session_state.info_box_visible:
            display_building_summary()


if __name__ == "__main__":
    main()
