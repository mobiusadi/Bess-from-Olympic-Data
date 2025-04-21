import dash
from dash import dcc, html, Input, Output, State, clientside_callback
import dash_leaflet as dl
import pandas as pd
from dash.exceptions import PreventUpdate
import re

# Read data from Excel or CSV
try:
    df = pd.read_excel('bess_data.xlsx', engine='openpyxl')
    print(f"Loaded {len(df)} records from bess_data.xlsx")
except FileNotFoundError:
    try:
        df = pd.read_csv('bess_data.csv')
        print(f"Loaded {len(df)} records from bess_data.csv")
    except FileNotFoundError:
        print("Error: Neither bess_data.xlsx nor bess_data.csv found")
        # Fallback data
        df = pd.DataFrame({
            'index': range(5),
            'Location': [
                'Moss Landing, CA', 'Surprise, AZ', 'Escondido, CA', 'Liverpool, UK', 'Tokyo, Japan'
            ],
            'Custom location (Lat,Lon)': [
                '(36.5786, -121.6954)', '(33.6391, -112.4128)', '(33.1192, -117.0864)',
                '(53.4084, -2.9916)', '(35.6762, 139.6503)'
            ],
            'Country': ['USA', 'USA', 'USA', 'United Kingdom', 'Japan'],
            'Event Date': ['2022-09-04', '2019-04-19', '2020-12-05', '2021-02-15', '2023-03-10'],
            'Application': ['Energy Storage', 'Grid Support', 'Renewable Integration', 'Energy Storage', 'Backup Power'],
            'Cause': ['Thermal Runaway', 'Overheating', 'Battery Failure', 'Electrical Fault', 'Unknown']
        })

# Ensure required columns
required_columns = ['Location', 'Custom location (Lat,Lon)', 'Event Date', 'Application', 'Cause']
for col in required_columns:
    if col not in df.columns:
        raise ValueError(f"Missing required column: {col}")

# Add index if not present
if 'index' not in df.columns:
    df['index'] = range(len(df))
df['index'] = df['index'].astype(int)

# Parse Custom location (Lat,Lon)
def parse_lat_lon(coord):
    try:
        # Extract numbers from string like '(36.5786, -121.6954)'
        match = re.match(r'\s*\(\s*([-\d.]+)\s*,\s*([-\d.]+)\s*\)', str(coord))
        if match:
            lat, lon = float(match.group(1)), float(match.group(2))
            return lat, lon
        return None, None
    except:
        return None, None

df[['latitude', 'longitude']] = df['Custom location (Lat,Lon)'].apply(
    lambda x: pd.Series(parse_lat_lon(x))
)

# Check for missing coordinates
missing_coords = df[df['latitude'].isna() | df['longitude'].isna()]
if not missing_coords.empty:
    print(f"Warning: {len(missing_coords)} rows have invalid/missing coordinates:")
    print(missing_coords[['Location', 'Custom location (Lat,Lon)']])

# Drop rows with missing coordinates
df = df.dropna(subset=['latitude', 'longitude'])
print(f"Final dataset: {len(df)} records")

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
            ]
        ),
        html.Div(
            style={'width': '70%'},
            children=[
                dl.Map(
                    id='location-map',
                    center=[0, 0],
                    zoom=1,
                    children=[
                        dl.TileLayer(),
                        dl.LayerGroup(id='marker-layer', children=[
                            dl.CircleMarker(
                                center=[row['latitude'], row['longitude']],
                                radius=5,
                                color='blue',
                                fillOpacity=0.8,
                                id={'type': 'marker', 'index': i}
                            )
                            for i, row in df.iterrows()
                        ])
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