import dash
from dash import dcc, html, Input, Output, State, clientside_callback
import dash_leaflet as dl
import pandas as pd
from dash.exceptions import PreventUpdate
import re
from geopy.geocoders import Nominatim
import time
import os

# Initialize geocoder
geolocator = Nominatim(user_agent="bess_map")

# Geocode function
def geocode_location(location):
    try:
        loc = geolocator.geocode(location)
        return loc.latitude, loc.longitude if loc else (None, None)
    except:
        return None, None

# Verify file existence
data_file = 'bess_data.xlsx'
if not os.path.exists(data_file):
    print(f"Error: {data_file} not found in {os.getcwd()}")
else:
    print(f"Found {data_file} in {os.getcwd()}")

# Read data from Excel or CSV
try:
    df = pd.read_excel(data_file, engine='openpyxl')
    # Drop unnamed/empty columns
    df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
    print(f"Loaded {len(df)} records from {data_file}")
    print(f"Column names: {df.columns.tolist()}")
except Exception as e:
    try:
        df = pd.read_csv('bess_data.csv')
        df = df.loc[:, ~df.columns.str.contains('^Unnamed')]
        print(f"Loaded {len(df)} records from bess_data.csv")
    except Exception as e:
        print(f"Error loading data: {e}")
        # Fallback data
        df = pd.DataFrame({
            'index': range(5),
            'Location': [
                'Moss Landing, CA', 'Surprise, AZ', 'Escondido, CA', 'Liverpool, UK', 'Tokyo, Japan'
            ],
            'Lat': [36.5786, 33.6391, 33.1192, 53.4084, 35.6762],
            'Long': [-121.6954, -112.4128, -117.0864, -2.9916, 139.6503],
            'Country': ['USA', 'USA', 'USA', 'United Kingdom', 'Japan'],
            'Event Date': ['2022-09-04', '2019-04-19', '2020-12-05', '2021-02-15', '2023-03-10'],
            'Application': ['Energy Storage', 'Grid Support', 'Renewable Integration', 'Energy Storage', 'Backup Power'],
            'Cause': ['Thermal Runaway', 'Overheating', 'Battery Failure', 'Electrical Fault', 'Unknown']
        })

# Ensure required columns
required_columns = ['Location', 'Event Date', 'Application', 'Cause']
for col in required_columns:
    if col not in df.columns:
        raise ValueError(f"Missing required column: {col}")

# Add index if not present
if 'index' not in df.columns:
    df['index'] = range(len(df))
df['index'] = df['index'].astype(int)

# Check for Lat/Long columns first
if 'Lat' in df.columns and 'Long' in df.columns:
    df['latitude'] = pd.to_numeric(df['Lat'], errors='coerce')
    df['longitude'] = pd.to_numeric(df['Long'], errors='coerce')
    print("Using Lat and Long columns")
else:
    # Parse Custom location (Lat,Lon) as fallback
    def parse_lat_lon(coord):
        try:
            coord = str(coord).strip()
            if coord in ['nan', '', 'N/A']:
                return None, None
            # Clean Excel prefixes
            coord = coord.replace("='=", "(").replace("=", "").replace("'", "")
            # Match formats: (lat, lon), [lat, lon], lat, lon
            patterns = [
                r'\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)',  # (lat, lon)
                r'\s*\[\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\]',  # [lat, lon]
                r'\s*([-\d.]+)\s*,\s*([-\d.]+)\s*'          # lat, lon
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

# Geocode missing coordinates (limit to 10 to avoid rate limits)
missing_coords = df[df['latitude'].isna() | df['longitude'].isna()]
if not missing_coords.empty:
    print(f"Geocoding {min(len(missing_coords), 10)} rows with missing/invalid coordinates...")
    for idx in missing_coords.index[:10]:
        loc = df.loc[idx, 'Location']
        coords = geocode_location(loc)
        df.loc[idx, ['latitude', 'longitude']] = coords
        time.sleep(1)  # Rate limit
        print(f"Geocoded {loc}: {coords}")

# Final check for missing coordinates
missing_coords = df[df['latitude'].isna() | df['longitude'].isna()]
if not missing_coords.empty:
    print(f"Warning: {len(missing_coords)} rows still have invalid/missing coordinates:")
    print(missing_coords[['Location', 'Lat', 'Long']])

# Drop rows with missing coordinates
df = df.dropna(subset=['latitude', 'longitude'])
print(f"Final dataset: {len(df)} records")

# Warn if no data
if df.empty:
    print("Warning: No valid data after processing. Check 'Lat'/'Long' columns for valid numbers.")

# Calculate initial map center
if not df.empty:
    center_lat = df['latitude'].mean()
    center_lon = df['longitude'].mean()
    initial_center = [center_lat, center_lon]
    initial_zoom = 2
else:
    initial_center = [0, 0]
    initial_zoom = 1

app = dash.Dash(__name__)

# Layout
app.layout = html.Div(
    style={'display': 'flex', 'height': '100vh'},
    children=[
        html.Div(
            id='location-list',
            style={'width': '30%', 'overflowY': 'auto', 'padding': '20px'},
            children=[
                html.Div(
                    id={'type': 'location-item', 'index': i},
                    children=[
                        html.H3(f"{row['Location']}", style={'margin': 0}),
                        html.P(
                            f"Date: {row['Event Date']} | Application: {row['Application']} | Cause: {row['Cause']}",
                            style={'margin': 0, 'fontSize': '14px'}
                        )
                    ],
                    style={'marginBottom': '10px', 'padding': '10px', 'cursor': 'pointer'},
                    **{'data-index': i}
                )
                for i, row in df.iterrows()
            ] if not df.empty else [
                html.P("No data available. Check dataset for valid coordinates.")
            ]
        ),
        html.Div(
            style={'width': '70%'},
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
                                radius=5,
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

@app.callback(
    Output('marker-layer', 'children'),
    Output('location-list', 'children'),
    Output('selected-index', 'data'),
    Input({'type': 'location-item', 'index': dash.ALL}, 'n_clicks'),
    Input({'type': 'marker', 'index': dash.ALL}, 'n_clicks'),
    State('location-list', 'children'),
    State({'type': 'location-item', 'index': dash.ALL}, 'id'),
    prevent_initial_call=True
)
def update_app(n_clicks_list, n_clicks_markers, current_items, item_ids):
    print("update_app CALLED")
    print(f"n_clicks_list: {n_clicks_list}")
    print(f"n_clicks_markers: {n_clicks_markers}")
    ctx = dash.callback_context
    if not ctx.triggered_id:
        print("No triggered ID")
        raise PreventUpdate

    clicked_index = -1
    if isinstance(ctx.triggered_id, dict) and ctx.triggered_id.get('type') == 'location-item':
        clicked_index = int(ctx.triggered_id['index'])
        print(f"List click: Index {clicked_index}, Location: {df.iloc[clicked_index]['Location']}")
    elif isinstance(ctx.triggered_id, dict) and ctx.triggered_id.get('type') == 'marker':
        clicked_index = int(ctx.triggered_id['index'])
        print(f"Map click: Index {clicked_index}, Location: {df.iloc[clicked_index]['Location']}")
    else:
        print(f"Invalid trigger: {ctx.triggered_id}")
        raise PreventUpdate

    # Update markers
    markers = [
        dl.CircleMarker(
            center=[row['latitude'], row['longitude']],
            radius=10 if i == clicked_index else 5,
            color='red' if i == clicked_index else 'blue',
            fillColor='red' if i == clicked_index else 'blue',
            fillOpacity=0.8,
            id={'type': 'marker', 'index': i}
        )
        for i, row in df.iterrows()
    ]

    # Update list
    updated_items = [
        html.Div(
            id={'type': 'location-item', 'index': i},
            children=[
                html.H3(f"{row['Location']}", style={'margin': 0}),
                html.P(
                    f"Date: {row['Event Date']} | Application: {row['Application']} | Cause: {row['Cause']}",
                    style={'margin': 0, 'fontSize': '14px'}
                )
            ],
            style={
                'marginBottom': '10px',
                'padding': '10px',
                'cursor': 'pointer',
                'border': '2px solid red' if i == clicked_index else '1px solid black'
            },
            **{'data-index': i}
        )
        for i, row in df.iterrows()
    ]

    return markers, updated_items, clicked_index

# Clientside callback for scrolling and map centering
app.clientside_callback(
    """
    function(children, selected_index) {
        console.log("Clientside triggered: selected_index=" + selected_index);
        if (selected_index >= 0) {
            const highlighted = document.querySelector(`[data-index="${selected_index}"]`);
            if (highlighted) {
                highlighted.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }
            const map = window.dash_leaflet_map;
            if (map && window.dash_clientside_data && window.dash_clientside_data[selected_index]) {
                const [lat, lng] = window.dash_clientside_data[selected_index];
                map.setView([lat, lng], 8);
            } else {
                console.log("Map or data not available:", { map: !!map, data: window.dash_clientside_data });
            }
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output('location-list', 'id'),
    Input('location-list', 'children'),
    Input('selected-index', 'data')
)

# Inject coordinates for clientside centering
app.clientside_callback(
    """
    function() {
        console.log("Injecting coordinates");
        window.dash_clientside_data = %s;
        return window.dash_clientside.no_update;
    }
    """ % df[['latitude', 'longitude']].values.tolist(),
    Output('location-map', 'id'),
    Input('location-map', 'id')
)

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=8080)