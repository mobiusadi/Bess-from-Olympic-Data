import dash
from dash import dcc, html, Input, Output, State, clientside_callback, Patch
import dash_leaflet as dl
import pandas as pd
from dash.exceptions import PreventUpdate
import re
from geopy.geocoders import Nominatim
import time
import os
import pickle
import hashlib
import numpy as np

# Initialize geocoder
geolocator = Nominatim(user_agent="bess_map")

def geocode_location(location):
    try:
        loc = geolocator.geocode(location)
        return loc.latitude, loc.longitude if loc else (None, None)
    except:
        return None, None

# Scale marker radius based on Capacity (MW)
def scale_radius(capacity, min_radius=5, max_radius=20, max_capacity=None):
    if max_capacity is None:
        max_capacity = df['Capacity (MW)'].max() if 'Capacity (MW)' in df.columns else 1
    if max_capacity == 0 or pd.isna(capacity) or capacity <= 0:
        return min_radius
    # Linear scaling
    scaled = min_radius + (max_radius - min_radius) * (capacity / max_capacity)
    return round(scaled, 2)

# Verify file existence
data_file = 'bess_data.xlsx'
data_cache_file = 'bess_data_cache.pkl'
cards_cache_file = 'cards_cache.pkl'

# Check if data file has changed
def get_file_hash(file_path):
    if not os.path.exists(file_path):
        return None
    with open(file_path, 'rb') as f:
        return hashlib.md5(f.read()).hexdigest()

# Load or generate data
data_hash = get_file_hash(data_file)
df = None
if os.path.exists(data_cache_file):
    try:
        with open(data_cache_file, 'rb') as f:
            cached_data = pickle.load(f)
        if isinstance(cached_data, tuple) and len(cached_data) == 2:
            cached_df, cached_hash = cached_data
            if cached_hash == data_hash:
                df = cached_df
                print(f"Loaded {len(df)} records from data cache")
    except Exception as e:
        print(f"Error loading data cache: {e}")
        df = None

if df is None:
    if not os.path.exists(data_file):
        print(f"Error: {data_file} not found in {os.getcwd()}")
    else:
        print(f"Found {data_file} in {os.getcwd()}")
    try:
        df = pd.read_excel(data_file, engine='openpyxl')
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        print(f"Loaded {len(df)} records from {data_file}")
        print(f"Column names: {df.columns.tolist()}")
        # Process data
        df['Event Date'] = pd.to_datetime(df['Event Date'], errors='coerce')
        df = df.sort_values(by='Event Date', ascending=False).reset_index(drop=True)
        df['index'] = range(len(df))
        df['index'] = df['index'].astype(int)
        if 'Lat' in df.columns and 'Long' in df.columns:
            df['latitude'] = pd.to_numeric(df['Lat'], errors='coerce')
            df['longitude'] = pd.to_numeric(df['Long'], errors='coerce')
            print("Using Lat and Long columns")
        else:
            def parse_lat_lon(coord):
                try:
                    coord = str(coord).strip()
                    if coord in ['nan', '', 'N/A']:
                        return None, None
                    coord = coord.replace("='=", "(").replace("=", "").replace("'", "")
                    patterns = [
                        r'\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)',
                        r'\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]',
                        r'\s*([-\d.]+)\s*,\s*([-\d.]+)\s*'
                    ]
                    for pattern in patterns:
                        match = re.match(pattern, coord)
                        if match:
                            lat, lon = float(match.group(1)), float(match.group(2))
                            if -90 <= lat <= 90 and -180 <= lon <= 180:
                                print(f"Parsed coordinate: {coord} -> ({lat}, {lon})")
                                return lat, lon
                    print(f"Failed to parse coordinate: {coord}")
                    return None, None
                except Exception as e:
                    print(f"Error parsing coordinate {coord}: {e}")
                    return None, None

            df[['latitude', 'longitude']] = df['Custom location (Lat,Lon)'].apply(
                lambda x: pd.Series(parse_lat_lon(x))
            )
        # Geocode missing coordinates
        missing_coords = df[df['latitude'].isna() | df['longitude'].isna()]
        if not missing_coords.empty:
            print(f"Geocoding {min(len(missing_coords), 10)} rows...")
            for idx in missing_coords.index[:10]:
                loc = df.loc[idx, 'Location']
                coords = geocode_location(loc)
                df.loc[idx, ['latitude', 'longitude']] = coords
                time.sleep(1)
                print(f"Geocoded {loc}: {coords}")
        df = df.dropna(subset=['latitude', 'longitude'])
        # Ensure Capacity (MW) is numeric
        df['Capacity (MW)'] = pd.to_numeric(df['Capacity (MW)'], errors='coerce').fillna(0)
        with open(data_cache_file, 'wb') as f:
            pickle.dump((df, data_hash), f)
        print(f"Saved {len(df)} records to data cache")
    except Exception as e:
        print(f"Error loading data: {e}")
        df = pd.DataFrame({
            'index': range(5),
            'Location': ['Moss Landing, CA', 'Surprise, AZ', 'Escondido, CA', 'Liverpool, UK', 'Tokyo, Japan'],
            'Lat': [36.5786, 33.6391, 33.1192, 53.4084, 35.6762],
            'Long': [-121.6954, -112.4128, -117.0864, -2.9916, 139.6503],
            'Country': ['USA', 'USA', 'USA', 'United Kingdom', 'Japan'],
            'Event Date': ['2022-09-04', '2019-04-19', '2020-12-05', '2021-02-15', '2023-03-10'],
            'Application': ['Energy Storage', 'Grid Support', 'Renewable Integration', 'Energy Storage', 'Backup Power'],
            'Cause': ['Thermal Runaway', 'Overheating', 'Battery Failure', 'Electrical Fault', 'Unknown'],
            'Capacity (MW)': [400, 100, 200, 50, 300],
            'Capacity (MWh)': [1600, 400, 800, 200, 1200],
            'Source URL 1': ['https://example.com/1', 'https://example.com/2', 'https://example.com/3', 'https://example.com/4', 'https://example.com/5'],
            'Image URL 1': [None, None, 'https://www.staradvertiser.com/wp-content/uploads/2015/11/20120801_brk_windfarmmap.jpg', None, None]
        })

# Ensure required columns
required_columns = ['Location', 'Event Date', 'Application', 'Cause']
for col in required_columns:
    if col not in df.columns:
        raise ValueError(f"Missing required column: {col}")

# Ensure Capacity (MW) is numeric
df['Capacity (MW)'] = pd.to_numeric(df['Capacity (MW)'], errors='coerce').fillna(0)

print(f"Final dataset: {len(df)} records")

# Detect URL and image columns
url_columns = ['Source URL 1', 'Source URL 2', 'Source URL 3']
image_columns = ['Image URL 1']  # Only use Image URL 1 for now
print(f"Detected URL columns: {url_columns}")
print(f"Detected image columns: {image_columns}")

# Cache cards
def generate_cards():
    cards = [
        html.Div(
            id={'type': 'location-item', 'index': i},
            children=[
                html.Div(
                    style={'display': 'flex', 'alignItems': 'flex-start'},
                    children=[
                        html.Img(
                            src=row[image_columns[0]],
                            style={'maxWidth': '150px', 'height': 'auto', 'marginRight': '10px'}
                        ) if image_columns and pd.notnull(row[image_columns[0]]) and str(row[image_columns[0]]).startswith(('http://', 'https://'))
                        else html.Div(style={'width': '150px'}),  # Placeholder if no image
                        html.Div([
                            html.H3(f"{row['Location']}", style={'margin': 0, 'fontFamily': 'Arial, sans-serif'}),
                            html.Div([
                                html.P([
                                    html.Span(f"{col}: ", style={
                                        'fontWeight': 'bold',
                                        'fontFamily': 'Arial, sans-serif',
                                        'fontSize': '14px'
                                    }),
                                    html.A(
                                        str(row[col]),
                                        href=str(row[col]),
                                        target="_blank",
                                        style={
                                            'fontWeight': 'normal',
                                            'color': 'blue',
                                            'textDecoration': 'underline',
                                            'fontSize': '14px',
                                            'fontFamily': 'Arial, sans-serif'
                                        }
                                    ) if col in url_columns and pd.notnull(row[col]) and str(row[col]).startswith(('http://', 'https://'))
                                    else html.Span(
                                        f"{row[col].strftime('%Y-%m-%d') if col == 'Event Date' and pd.notnull(row[col]) else str(row[col])}",
                                        style={
                                            'fontWeight': 'bold' if col in ['Capacity (MW)', 'Capacity (MWh)'] else 'normal',
                                            'color': 'red' if col in ['Capacity (MW)', 'Capacity (MWh)'] else 'black',
                                            'fontSize': '18px' if col in ['Capacity (MW)', 'Capacity (MWh)'] else '14px',
                                            'fontFamily': 'Arial, sans-serif'
                                        }
                                    )
                                ], style={'margin': '2px 0'})
                                for col in df.columns if col not in ['index', 'latitude', 'longitude', 'Lat', 'Long', 'Image URL 1', 'Image URL 2', 'Image URL 3']
                            ], style={'marginTop': '5px'})
                        ])
                    ]
                )
            ],
            style={'marginBottom': '10px', 'padding': '10px', 'cursor': 'pointer', 'border': '1px solid black'},
            **{'data-index': i}
        )
        for i, row in df.iterrows()
    ]
    return cards

location_list_children = None
if os.path.exists(cards_cache_file):
    try:
        with open(cards_cache_file, 'rb') as f:
            cached_cards_data = pickle.load(f)
        if isinstance(cached_cards_data, tuple) and len(cached_cards_data) == 2:
            cached_cards, cached_hash = cached_cards_data
            if cached_hash == data_hash:
                location_list_children = cached_cards
                print("Loaded cards from cache")
    except Exception as e:
        print(f"Error loading cards cache: {e}")
        location_list_children = None

if location_list_children is None:
    location_list_children = generate_cards()
    with open(cards_cache_file, 'wb') as f:
        pickle.dump((location_list_children, data_hash), f)
    print("Generated and cached cards")

# Map center
if not df.empty:
    center_lat = df['latitude'].mean()
    center_lon = df['longitude'].mean()
    initial_center = [center_lat, center_lon]
    initial_zoom = 2
else:
    initial_center = [0, 0]
    initial_zoom = 1

app = dash.Dash(__name__)

# Layout without dcc.Loading to prevent white screen
app.layout = html.Div([
    html.H1("BESS Incident Map", style={'fontFamily': 'Arial, sans-serif', 'textAlign': 'center'}),
    html.P("Click a card or marker to view details.", style={'fontFamily': 'Arial, sans-serif', 'textAlign': 'center'}),
    html.Div(
        style={'display': 'flex', 'height': '100vh', 'fontFamily': 'Arial, sans-serif'},
        children=[
            html.Div(
                id='location-list',
                style={'width': '30%', 'overflowY': 'auto', 'padding': '20px'},
                children=location_list_children if not df.empty else [
                    html.P("No data available.", style={'fontFamily': 'Arial, sans-serif'})
                ]
            ),
            html.Div(
                style={'width': '70%', 'position': 'relative'},
                children=[
                    dl.Map(
                        id='location-map',
                        center=initial_center,
                        zoom=initial_zoom,
                        minZoom=2,
                        maxBounds=[[-90, -180], [90, 180]],
                        maxBoundsViscosity=1.0,
                        children=[
                            dl.TileLayer(),
                            dl.LayerGroup(id='marker-layer', children=[
                                dl.CircleMarker(
                                    center=[row['latitude'], row['longitude']],
                                    radius=scale_radius(row['Capacity (MW)']),
                                    color='blue',
                                    fillColor='blue',
                                    fillOpacity=0.8,
                                    id={'type': 'marker', 'index': i}
                                )
                                for i, row in df.iterrows()
                            ] if not df.empty else [])
                        ],
                        style={'width': '100%', 'height': '100vh'}
                    ),
                    dcc.Store(id='selected-index', data=-1)
                ]
            )
        ]
    )
])

# Server-side callback to update marker-layer
@app.callback(
    Output('marker-layer', 'children'),
    Input('selected-index', 'data'),
    prevent_initial_call=True
)
def update_markers(selected_index):
    print(f"Updating markers: selected_index={selected_index}")
    patched_markers = Patch()
    for i in range(len(df)):
        radius = scale_radius(df.iloc[i]['Capacity (MW)'])
        color = 'red' if i == selected_index else 'blue'
        patched_markers.append(
            dl.CircleMarker(
                center=[df.iloc[i]['latitude'], df.iloc[i]['longitude']],
                radius=radius * 1.5 if i == selected_index else radius,
                color=color,
                fillColor=color,
                fillOpacity=0.8,
                id={'type': 'marker', 'index': i}
            )
        )
    return patched_markers

# Clientside callback for card updates and map centering
app.clientside_callback(
    """
    function(n_clicks_list, n_clicks_markers, selected_index, children) {
        // Debounce clicks
        let lastClickTime = window.lastClickTime || 0;
        const now = Date.now();
        if (now - lastClickTime < 300) return window.dash_clientside.no_update;
        window.lastClickTime = now;

        console.log("Clientside update: selected_index=" + selected_index);

        // Update card styles
        const updated_children = children.map((child, i) => {
            child.props.style = {
                ...child.props.style,
                border: i === selected_index ? '2px solid red' : '1px solid black'
            };
            return child;
        });

        // Center map on selected marker
        if (selected_index >= 0) {
            const highlighted = document.querySelector(`[data-index="${selected_index}"]`);
            if (highlighted) {
                highlighted.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            let attempts = 0;
            const maxAttempts = 50;
            const checkMap = setInterval(() => {
                if (window.dash_leaflet_map && window.dash_clientside_data && window.dash_clientside_data[selected_index]) {
                    const [lat, lng] = window.dash_clientside_data[selected_index];
                    window.dash_leaflet_map.setView([lat, lng], 8);
                    clearInterval(checkMap);
                    console.log("Map centered on index " + selected_index);
                } else if (attempts >= maxAttempts) {
                    console.log("Map centering timeout");
                    clearInterval(checkMap);
                }
                attempts++;
            }, 100);
        }

        return updated_children;
    }
    """,
    Output('location-list', 'children'),
    [Input({'type': 'location-item', 'index': dash.ALL}, 'n_clicks'),
     Input({'type': 'marker', 'index': dash.ALL}, 'n_clicks'),
     Input('selected-index', 'data')],
    State('location-list', 'children')
)

# Clientside callback to inject coordinates
app.clientside_callback(
    """
    function(map_id) {
        console.log("Injecting coordinates for map_id: " + map_id);
        window.dash_clientside_data = %s;
        return window.dash_clientside.no_update;
    }
    """ % (df[['latitude', 'longitude']].values.tolist() if not df.empty else []),
    Output('location-map', 'id'),
    Input('location-map', 'id')
)

# Server-side callback to update selected-index
@app.callback(
    Output('selected-index', 'data'),
    [Input({'type': 'location-item', 'index': dash.ALL}, 'n_clicks'),
     Input({'type': 'marker', 'index': dash.ALL}, 'n_clicks')],
    prevent_initial_call=True
)
def update_selected_index(n_clicks_list, n_clicks_markers):
    ctx = dash.callback_context
    if not ctx.triggered_id:
        raise PreventUpdate
    clicked_index = ctx.triggered_id['index']
    print(f"Selected index: {clicked_index}, Location: {df.iloc[clicked_index]['Location']}")
    return clicked_index

# Expose server for Gunicorn
server = app.server

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)

# Future image caching:
# 1. Create /images/ directory.
# 2. Download images from Image URL 1, Image URL 2, Image URL 3 using requests.
# 3. Save as /images/{index}_{col}.jpg (e.g., /images/2_Image_URL_1.jpg).
# 4. Serve images via Dash assets: app.get_asset_url(f"{index}_{col}.jpg").
# 5. Update html.Img src to use local paths.