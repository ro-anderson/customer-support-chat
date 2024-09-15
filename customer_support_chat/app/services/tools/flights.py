from vectorizer.app.vectordb.vectordb import VectorDB
from customer_support_chat.app.core.settings import get_settings
from langchain_core.tools import tool
from langchain_core.runnables import RunnableConfig
import sqlite3
from typing import Optional, Union, List, Dict
from datetime import datetime, date
import pytz

settings = get_settings()
db = settings.SQLITE_DB_PATH
flights_vectordb = VectorDB(table_name="flights", collection_name="flights_collection")

@tool
def fetch_user_flight_information(*, config: RunnableConfig) -> List[Dict]:
    """Fetch all tickets for the user along with corresponding flight information and seat assignments."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError("No passenger ID configured.")

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    query = """
    SELECT 
        t.ticket_no, t.book_ref,
        f.flight_id, f.flight_no, f.departure_airport, f.arrival_airport, f.scheduled_departure, f.scheduled_arrival,
        bp.seat_no, tf.fare_conditions
    FROM 
        tickets t
        JOIN ticket_flights tf ON t.ticket_no = tf.ticket_no
        JOIN flights f ON tf.flight_id = f.flight_id
        LEFT JOIN boarding_passes bp ON bp.ticket_no = t.ticket_no AND bp.flight_id = f.flight_id
    WHERE 
        t.passenger_id = ?
    """
    cursor.execute(query, (passenger_id,))
    rows = cursor.fetchall()
    column_names = [column[0] for column in cursor.description]
    results = [dict(zip(column_names, row)) for row in rows]

    cursor.close()
    conn.close()

    return results

@tool
def search_flights(
    query: str,
    limit: int = 20,
) -> List[Dict]:
    """Search for flights based on a natural language query."""
    search_results = flights_vectordb.search(query, limit=limit)

    flights = []
    for result in search_results:
        payload = result.payload
        flights.append({
            "flight_id": payload["metadata"]["flight_id"],
            "flight_no": payload["metadata"]["flight_no"],
            "departure_airport": payload["metadata"]["departure_airport"],
            "arrival_airport": payload["metadata"]["arrival_airport"],
            "scheduled_departure": payload["metadata"]["scheduled_departure"],
            "scheduled_arrival": payload["metadata"]["scheduled_arrival"],
            "status": payload["metadata"]["status"],
            "aircraft_code": payload["metadata"]["aircraft_code"],
            "actual_departure": payload["metadata"]["actual_departure"],
            "actual_arrival": payload["metadata"]["actual_arrival"],
            "chunk": payload["content"],
            "similarity": result.score,
        })
    return flights

@tool
def update_ticket_to_new_flight(
    ticket_no: str, new_flight_id: int, *, config: RunnableConfig
) -> str:
    """Update the user's ticket to a new valid flight."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError("No passenger ID configured.")

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Check if the ticket exists and belongs to the passenger
    cursor.execute(
        "SELECT * FROM tickets WHERE ticket_no = ? AND passenger_id = ?",
        (ticket_no, passenger_id),
    )
    ticket = cursor.fetchone()
    if not ticket:
        conn.close()
        return f"Ticket {ticket_no} not found for passenger {passenger_id}."

    # Update the flight in ticket_flights
    cursor.execute(
        "UPDATE ticket_flights SET flight_id = ? WHERE ticket_no = ?",
        (new_flight_id, ticket_no),
    )
    conn.commit()

    if cursor.rowcount > 0:
        conn.close()
        return f"Ticket {ticket_no} successfully updated to flight {new_flight_id}."
    else:
        conn.close()
        return f"Failed to update ticket {ticket_no}."

@tool
def cancel_ticket(ticket_no: str, *, config: RunnableConfig) -> str:
    """Cancel the user's ticket and remove it from the database."""
    configuration = config.get("configurable", {})
    passenger_id = configuration.get("passenger_id", None)
    if not passenger_id:
        raise ValueError("No passenger ID configured.")

    conn = sqlite3.connect(db)
    cursor = conn.cursor()

    # Check if the ticket exists and belongs to the passenger
    cursor.execute(
        "SELECT * FROM tickets WHERE ticket_no = ? AND passenger_id = ?",
        (ticket_no, passenger_id),
    )
    ticket = cursor.fetchone()
    if not ticket:
        conn.close()
        return f"Ticket {ticket_no} not found for passenger {passenger_id}."

    # Delete from ticket_flights
    cursor.execute(
        "DELETE FROM ticket_flights WHERE ticket_no = ?",
        (ticket_no,),
    )
    # Delete from tickets
    cursor.execute(
        "DELETE FROM tickets WHERE ticket_no = ?",
        (ticket_no,),
    )
    conn.commit()

    conn.close()
    return f"Ticket {ticket_no} successfully cancelled."
