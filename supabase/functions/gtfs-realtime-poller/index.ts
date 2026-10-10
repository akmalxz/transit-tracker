import { serve } from "https://deno.land/std@0.168.0/http/server.ts"
import { createClient } from 'https://esm.sh/@supabase/supabase-js@2'
import GtfsRealtimeBindings from "https://esm.sh/gtfs-realtime-bindings@1.1.1"

serve(async (req) => {
  try {
    console.log("Fetching GTFS Realtime data...")
    
    // 1. Fetch the Protobuf feed
    const url = "https://api.data.gov.my/gtfs-realtime/vehicle-position/prasarana?category=rapid-bus-kl"
    const response = await fetch(url)
    const buffer = await response.arrayBuffer()
    
    // 2. Decode the binary data
    const feed = GtfsRealtimeBindings.transit_realtime.FeedMessage.decode(new Uint8Array(buffer))
    
    const positions = []
    for (const entity of feed.entity) {
      if (entity.vehicle) {
        const v = entity.vehicle
        positions.push({
          vehicle_id: v.vehicle?.id,
          trip_id: v.trip?.tripId,
          route_id: v.trip?.routeId,
          latitude: v.position?.latitude,
          longitude: v.position?.longitude,
          current_status: v.currentStatus?.toString(),
          timestamp: v.timestamp ? new Date(v.timestamp.toNumber() * 1000).toISOString() : new Date().toISOString()
        })
      }
    }

    if (positions.length === 0) {
      return new Response(JSON.stringify({ message: "No vehicles found" }), { status: 200 })
    }

    console.log(`Parsed ${positions.length} buses. Upserting to Supabase...`)

    // 3. Connect to Supabase
    // These environment variables are automatically injected by the Edge Function runtime
    const supabase = createClient(
      Deno.env.get('SUPABASE_URL') ?? '',
      Deno.env.get('SUPABASE_SERVICE_ROLE_KEY') ?? '' // Bypasses RLS to allow backend writes
    )

    // 4. Upsert Data (Update coordinates if bus exists, insert if new)
    const { error } = await supabase
      .from('vehicle_positions')
      .upsert(positions, { onConflict: 'vehicle_id' })

    if (error) throw error

    return new Response(JSON.stringify({ success: true, count: positions.length }), {
      headers: { "Content-Type": "application/json" },
      status: 200,
    })

  } catch (error) {
    console.error("Error processing GTFS feed:", error)
    return new Response(JSON.stringify({ error: error.message }), { status: 500 })
  }
})