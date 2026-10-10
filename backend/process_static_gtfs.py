import os
import requests
import zipfile
import io
import pandas as pd
from sqlalchemy import create_engine, text

def main():
    print("Starting GTFS-Static Ingestion...")
    
    # 1. Connect to Supabase
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        raise ValueError("DATABASE_URL environment variable is not set!")
        
    # SQLAlchemy requires 'postgresql://' instead of 'postgres://'
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
        
    engine = create_engine(db_url)
    
    # 2. Download the GTFS-Static ZIP file for Rapid KL Buses
    url = "https://api.data.gov.my/gtfs-static/prasarana?category=rapid-bus-kl"
    print(f"Downloading data from: {url}")
    
    response = requests.get(url)
    response.raise_for_status()
    
    print("Extracting ZIP file...")
    with zipfile.ZipFile(io.BytesIO(response.content)) as z:
        z.extractall("gtfs_data")
        
    # 3. Parse the required files using Pandas
    print("Parsing GTFS CSV files...")
    
    # Cast IDs to string to avoid dropping leading zeros
    routes_df = pd.read_csv("gtfs_data/routes.txt", dtype=str)
    stops_df = pd.read_csv("gtfs_data/stops.txt", dtype=str)
    trips_df = pd.read_csv("gtfs_data/trips.txt", dtype=str)
    
    # Cast coordinates back to float
    stops_df['stop_lat'] = stops_df['stop_lat'].astype(float)
    stops_df['stop_lon'] = stops_df['stop_lon'].astype(float)
    
    # Filter to only the columns our database expects
    routes_df = routes_df[['route_id', 'route_short_name', 'route_long_name', 'route_type']]
    stops_df = stops_df[['stop_id', 'stop_name', 'stop_lat', 'stop_lon']]
    
    # Handle shape_id safely (some transit feeds occasionally omit it)
    trip_cols = ['trip_id', 'route_id', 'service_id']
    if 'shape_id' in trips_df.columns:
         trip_cols.append('shape_id')
    trips_df = trips_df[trip_cols]
    
    # 4. Update the Supabase Database
    print("Updating Database...")
    
    # Using a transaction context manager to ensure data integrity
    with engine.begin() as conn:
        print("Clearing old static data...")
        # TRUNCATE removes all rows. CASCADE ensures the foreign key relationships don't block the deletion.
        conn.execute(text("TRUNCATE TABLE trips, routes, stops CASCADE;"))
        
        print(f"Inserting {len(routes_df)} routes...")
        routes_df.to_sql('routes', conn, if_exists='append', index=False)
        
        print(f"Inserting {len(stops_df)} stops...")
        stops_df.to_sql('stops', conn, if_exists='append', index=False)
        
        print(f"Inserting {len(trips_df)} trips...")
        trips_df.to_sql('trips', conn, if_exists='append', index=False)
        
        print("Generating PostGIS Geospatial Points for stops...")
        # This converts the standard lat/lon numbers into PostGIS geometry objects mapped to the Earth's surface (SRID 4326)
        conn.execute(text("UPDATE stops SET geom = ST_SetSRID(ST_MakePoint(stop_lon, stop_lat), 4326);"))
        
    print("GTFS-Static Ingestion completed successfully!")

if __name__ == "__main__":
    main()