import dash
from dash import dcc, html, Input, Output, dash_table
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import json
import os
from main import GoogleRoutingClient, ValhallaRoutingClient, Costing, load_json
from dotenv import load_dotenv
import logging

# Load environment variables
load_dotenv()
load_dotenv('.env.local', override=True)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class RoutingDashboard:
    def __init__(self):
        self.app = dash.Dash(__name__)
        self.routing_client = self._setup_routing_client()
        self.google_request_count = 0  # Track Google API requests
        self.setup_layout()
        self.setup_callbacks()
        
    def _setup_routing_client(self):
        """Setup the routing client based on environment variables"""
        USE_GOOGLE = os.getenv("USE_GOOGLE", "false").lower() == "true"
        
        if USE_GOOGLE:
            GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
            if not GOOGLE_API_KEY:
                raise ValueError("GOOGLE_API_KEY not found in environment variables")
            logger.info("Using Google Routing Client")
            return GoogleRoutingClient(GOOGLE_API_KEY)
        else:
            VALHALLA_URL = os.getenv("VALHALLA_URL", "http://[::1]:9000/valhalla")
            NOMINATIM_URL = os.getenv("NOMINATIM_URL", "http://[::1]:9000/nominatim")
            logger.info("Using Valhalla Routing Client")
            return ValhallaRoutingClient(VALHALLA_URL, NOMINATIM_URL)
    
    def load_and_process_data(self, costing="auto"):
        """Load destinations and origins, calculate routes"""
        try:
            destinations = load_json("destinations.json")
            origins = load_json("home_options.json")
        except FileNotFoundError:
            logger.error("destinations.json or home_options.json not found")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        
        # Geocode locations
        for dest in destinations:
            try:
                dest["coords"] = self.routing_client.geocode(dest["name"])
                if isinstance(self.routing_client, GoogleRoutingClient):
                    self.google_request_count += 1
            except Exception as e:
                logger.error(f"Failed to geocode destination {dest['name']}: {e}")
                dest["coords"] = [0, 0]
        
        for origin in origins:
            try:
                origin["coords"] = self.routing_client.geocode(origin["name"])
                if isinstance(self.routing_client, GoogleRoutingClient):
                    self.google_request_count += 1
            except Exception as e:
                logger.error(f"Failed to geocode origin {origin['name']}: {e}")
                origin["coords"] = [0, 0]
        
        # Calculate routes and scores
        route_data = []
        origin_scores = []
        
        for origin in origins:
            total_score = 0
            valid_routes = 0
            
            for dest in destinations:
                try:
                    response = self.routing_client.get_route(
                        origin["coords"], dest["coords"], costing=costing
                    )
                    if isinstance(self.routing_client, GoogleRoutingClient):
                        self.google_request_count += 1
                    
                    if "trip" in response and "summary" in response["trip"]:
                        time_min = response["trip"]["summary"].get("time")
                        if time_min is not None:
                            weighted_time = time_min * dest.get("weight", 1.0)
                            total_score += weighted_time
                            valid_routes += 1
                            
                            route_data.append({
                                "origin": origin["name"],
                                "destination": dest["name"],
                                "travel_time": time_min,
                                "weight": dest.get("weight", 1.0),
                                "weighted_time": weighted_time,
                                "origin_lat": origin["coords"][0],
                                "origin_lng": origin["coords"][1],
                                "dest_lat": dest["coords"][0],
                                "dest_lng": dest["coords"][1]
                            })
                except Exception as e:
                    logger.error(f"Route calculation failed: {origin['name']} -> {dest['name']}: {e}")
            
            if valid_routes > 0:
                avg_score = total_score / valid_routes
                origin_scores.append({
                    "origin": origin["name"],
                    "total_score": total_score,
                    "avg_score": avg_score,
                    "valid_routes": valid_routes,
                    "lat": origin["coords"][0],
                    "lng": origin["coords"][1]
                })
        
        # Log summary
        logger.info(f"Processed {len(origins)} origins and {len(destinations)} destinations")
        if isinstance(self.routing_client, GoogleRoutingClient):
            logger.info(f"Total Google API requests: {self.google_request_count}")
        
        # Create DataFrames
        routes_df = pd.DataFrame(route_data)
        origins_df = pd.DataFrame(origin_scores)
        destinations_df = pd.DataFrame([{
            "name": dest["name"],
            "weight": dest.get("weight", 1.0),
            "lat": dest["coords"][0],
            "lng": dest["coords"][1]
        } for dest in destinations])
        
        return routes_df, origins_df, destinations_df
    
    def setup_layout(self):
        """Setup the dashboard layout"""
        self.app.layout = html.Div([
            html.H1("Home Location Optimizer Dashboard", 
                   style={'textAlign': 'center', 'marginBottom': 30}),
            
            # Controls
            html.Div([
                html.Div([
                    html.Label("Transportation Mode:"),
                    dcc.Dropdown(
                        id='costing-dropdown',
                        options=[
                            {'label': 'Auto/Car', 'value': 'auto'},
                            {'label': 'Bicycle', 'value': 'bicycle'},
                            {'label': 'Walking', 'value': 'pedestrian'},
                            {'label': 'Public Transit', 'value': 'bus'},
                            {'label': 'Motor Scooter', 'value': 'motor_scooter'},
                            {'label': 'Truck', 'value': 'truck'}
                        ],
                        value='auto',
                        style={'width': '200px'}
                    )
                ], style={'width': '48%', 'display': 'inline-block'}),
                
                html.Div([
                    html.Button('Refresh Data', id='refresh-button', 
                               style={'padding': '10px 20px', 'backgroundColor': '#007bff', 
                                     'color': 'white', 'border': 'none', 'borderRadius': '5px'})
                ], style={'width': '48%', 'float': 'right', 'textAlign': 'right'})
            ], style={'marginBottom': 30}),
            
            # Main content
            html.Div(id='dashboard-content')
        ])
    
    def create_dashboard_content(self, routes_df, origins_df, destinations_df):
        """Create the main dashboard content"""
        if routes_df.empty:
            return html.Div([
                html.H3("No data available", style={'textAlign': 'center'}),
                html.P("Make sure destinations.json and home_options.json files exist and contain valid data.")
            ])
        
        # Map
        map_fig = go.Figure()
        
        # Add origin points
        if not origins_df.empty:
            map_fig.add_trace(go.Scattermapbox(
                lat=origins_df['lat'],
                lon=origins_df['lng'],
                mode='markers',
                marker=dict(size=12, color='blue'),
                text=origins_df['origin'],
                name='Potential Homes',
                hovertemplate='<b>%{text}</b><br>Avg Score: %{customdata:.2f}<extra></extra>',
                customdata=origins_df['avg_score']
            ))
        
        # Add destination points
        if not destinations_df.empty:
            map_fig.add_trace(go.Scattermapbox(
                lat=destinations_df['lat'],
                lon=destinations_df['lng'],
                mode='markers',
                marker=dict(size=10, color='red'),
                text=destinations_df['name'],
                name='Destinations',
                hovertemplate='<b>%{text}</b><br>Weight: %{customdata}<extra></extra>',
                customdata=destinations_df['weight']
            ))
        
        # Set map layout
        center_lat = origins_df['lat'].mean() if not origins_df.empty else 0
        center_lng = origins_df['lng'].mean() if not origins_df.empty else 0
        
        map_fig.update_layout(
            mapbox=dict(
                style="open-street-map",
                center=dict(lat=center_lat, lon=center_lng),
                zoom=11
            ),
            height=500,
            margin=dict(l=0, r=0, t=0, b=0)
        )
        
        # Origin scores bar chart
        origins_chart = px.bar(
            origins_df.sort_values('avg_score'),
            x='avg_score',
            y='origin',
            orientation='h',
            title='Average Travel Time by Location (Lower is Better)',
            labels={'avg_score': 'Average Weighted Time (minutes)', 'origin': 'Location'}
        )
        origins_chart.update_layout(height=400)
        
        # Routes heatmap
        if not routes_df.empty:
            pivot_data = routes_df.pivot(index='origin', columns='destination', values='travel_time')
            heatmap_fig = px.imshow(
                pivot_data,
                aspect='auto',
                title='Travel Times Heatmap (minutes)',
                labels=dict(x="Destinations", y="Origins", color="Travel Time (min)")
            )
            heatmap_fig.update_layout(height=400)
        else:
            heatmap_fig = go.Figure()
            heatmap_fig.add_annotation(text="No route data available", 
                                     xref="paper", yref="paper", x=0.5, y=0.5)
        
        # Summary statistics
        summary_stats = html.Div([
            html.H3("Summary Statistics"),
            html.Div([
                html.Div([
                    html.H4(f"{len(origins_df)}", style={'color': 'blue', 'margin': 0}),
                    html.P("Potential Locations", style={'margin': 0})
                ], style={'textAlign': 'center', 'width': '24%', 'display': 'inline-block'}),
                
                html.Div([
                    html.H4(f"{len(destinations_df)}", style={'color': 'red', 'margin': 0}),
                    html.P("Destinations", style={'margin': 0})
                ], style={'textAlign': 'center', 'width': '24%', 'display': 'inline-block'}),
                
                html.Div([
                    html.H4(f"{len(routes_df)}", style={'color': 'green', 'margin': 0}),
                    html.P("Calculated Routes", style={'margin': 0})
                ], style={'textAlign': 'center', 'width': '24%', 'display': 'inline-block'}),
                
                html.Div([
                    html.H4(f"{origins_df['avg_score'].min():.1f} min" if not origins_df.empty else "N/A", 
                           style={'color': 'orange', 'margin': 0}),
                    html.P("Best Average Time", style={'margin': 0})
                ], style={'textAlign': 'center', 'width': '24%', 'display': 'inline-block'})
            ])
        ], style={'marginBottom': 30, 'padding': '20px', 'backgroundColor': '#f8f9fa', 'borderRadius': '10px'})
        
        # Data table
        table_data = routes_df[['origin', 'destination', 'travel_time', 'weight', 'weighted_time']].round(2)
        
        return html.Div([
            summary_stats,
            
            html.Div([
                html.Div([
                    html.H3("Interactive Map"),
                    dcc.Graph(figure=map_fig)
                ], style={'width': '50%', 'display': 'inline-block'}),
                
                html.Div([
                    html.H3("Location Rankings"),
                    dcc.Graph(figure=origins_chart)
                ], style={'width': '50%', 'display': 'inline-block'})
            ]),
            
            html.Div([
                html.H3("Travel Times Heatmap"),
                dcc.Graph(figure=heatmap_fig)
            ], style={'marginTop': 30}),
            
            html.Div([
                html.H3("Detailed Route Data"),
                dash_table.DataTable(
                    data=table_data.to_dict('records'),
                    columns=[
                        {'name': 'Origin', 'id': 'origin'},
                        {'name': 'Destination', 'id': 'destination'},
                        {'name': 'Travel Time (min)', 'id': 'travel_time', 'type': 'numeric', 'format': {'specifier': '.1f'}},
                        {'name': 'Weight', 'id': 'weight', 'type': 'numeric', 'format': {'specifier': '.1f'}},
                        {'name': 'Weighted Time', 'id': 'weighted_time', 'type': 'numeric', 'format': {'specifier': '.1f'}}
                    ],
                    sort_action='native',
                    filter_action='native',
                    page_size=15,
                    style_cell={'textAlign': 'left'},
                    style_data_conditional=[
                        {
                            'if': {'row_index': 'odd'},
                            'backgroundColor': 'rgb(248, 248, 248)'
                        }
                    ]
                )
            ], style={'marginTop': 30})
        ])
    
    def setup_callbacks(self):
        """Setup interactive callbacks"""
        @self.app.callback(
            Output('dashboard-content', 'children'),
            [Input('refresh-button', 'n_clicks'),
             Input('costing-dropdown', 'value')]
        )
        def update_dashboard(n_clicks, costing):
            routes_df, origins_df, destinations_df = self.load_and_process_data(costing)
            return self.create_dashboard_content(routes_df, origins_df, destinations_df)
    
    def run(self, debug=True, host='127.0.0.1', port=8050):
        """Run the dashboard"""
        print(f"Starting dashboard at http://{host}:{port}")
        self.app.run(debug=debug, host=host, port=port)

if __name__ == "__main__":
    dashboard = RoutingDashboard()
    dashboard.run()
