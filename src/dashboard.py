import dash
from dash import dcc, html, Input, Output, dash_table
import plotly.express as px
import plotly.graph_objects as go
import pandas as pd
import json
import os
from main import setup_routing_client, load_and_process_routing_data, GoogleRoutingClient
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
        self.routing_client = setup_routing_client()
        self.setup_layout()
        self.setup_callbacks()
        
    def load_and_process_data(self, costing="auto"):
        """Load destinations and origins, calculate routes"""
        try:
            # Use the centralized function from main.py
            route_data, origin_scores, destinations = load_and_process_routing_data(self.routing_client, costing)
            
            # Convert to pandas DataFrames with proper column mapping
            routes_df = pd.DataFrame([{
                "origin": route["origin"],
                "destination": route["destination"],
                "travel_time": route["travel_time"],
                "weight": route["weight"],
                "weighted_time": route["weighted_time"],
                "departure_time_to": route["departure_time_to"],
                "departure_time_from": route["departure_time_from"],
                "day_of_week": route["day_of_week"],
                "origin_lat": route["origin_coords"][0],
                "origin_lng": route["origin_coords"][1],
                "dest_lat": route["dest_coords"][0],
                "dest_lng": route["dest_coords"][1],
                "traffic_time": route.get("traffic_time", route["travel_time"]),
                "normal_time": route.get("normal_time", route["travel_time"]),
                "traffic_impact_percent": route.get("traffic_impact_percent", 0)
            } for route in route_data])
            origins_df = pd.DataFrame([{
                "origin": score["name"],
                "total_score": score["total_score"],
                "avg_score": score["avg_score"],
                "valid_routes": score["valid_routes"],
                "lat": score["coords"][0],
                "lng": score["coords"][1]
            } for score in origin_scores])
            
            destinations_df = pd.DataFrame([{
                "name": dest["name"],
                "weight": dest.get("weight", 1.0),
                "departure_time_to": dest.get("departure_time_to", "N/A"),
                "departure_time_from": dest.get("departure_time_from", "N/A"),
                "day_of_week": dest.get("day_of_week", "N/A"),
                "lat": dest["coords"][0],
                "lng": dest["coords"][1]
            } for dest in destinations])
            
            # Log summary
            logger.info(f"Processed {len(origin_scores)} origins and {len(destinations)} destinations")
            if isinstance(self.routing_client.routing_client, GoogleRoutingClient):
                logger.info("Using Google routing client through cache")
            
            return routes_df, origins_df, destinations_df
            
        except FileNotFoundError:
            logger.error("destinations.json or home_options.json not found")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
        except Exception as e:
            logger.error(f"Error processing routing data: {e}")
            return pd.DataFrame(), pd.DataFrame(), pd.DataFrame()
    
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
            hover_text = destinations_df.apply(
                lambda row: f"<b>{row['name']}</b><br>Weight: {row['weight']}<br>"
                           f"Departure To: {row['departure_time_to']}<br>"
                           f"Departure From: {row['departure_time_from']}<br>"
                           f"Day: {row['day_of_week']}", axis=1
            )
            map_fig.add_trace(go.Scattermapbox(
                lat=destinations_df['lat'],
                lon=destinations_df['lng'],
                mode='markers',
                marker=dict(size=10, color='red'),
                text=destinations_df['name'],
                name='Destinations',
                hovertemplate='%{customdata}<extra></extra>',
                customdata=hover_text
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
        table_data = routes_df[['origin', 'destination', 'travel_time', 'traffic_time', 'normal_time', 
                               'traffic_impact_percent', 'weight', 'weighted_time', 
                               'departure_time_to', 'departure_time_from', 'day_of_week']].round(2)
        
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
                        {'name': 'Traffic Time (min)', 'id': 'traffic_time', 'type': 'numeric', 'format': {'specifier': '.1f'}},
                        {'name': 'Normal Time (min)', 'id': 'normal_time', 'type': 'numeric', 'format': {'specifier': '.1f'}},
                        {'name': 'Traffic Impact (%)', 'id': 'traffic_impact_percent', 'type': 'numeric', 'format': {'specifier': '.1f'}},
                        {'name': 'Weight', 'id': 'weight', 'type': 'numeric', 'format': {'specifier': '.1f'}},
                        {'name': 'Weighted Time', 'id': 'weighted_time', 'type': 'numeric', 'format': {'specifier': '.1f'}},
                        {'name': 'Departure To', 'id': 'departure_time_to'},
                        {'name': 'Departure From', 'id': 'departure_time_from'},
                        {'name': 'Day of Week', 'id': 'day_of_week'}
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
