from datetime import datetime
from typing import List

from postgrest.exceptions import APIError

from ..database.supabase_client import supabase
from ..models.session import Session
from ..schemas.session import Participant
from ..services.user_service import get_or_create_users


def create_session(session: Session, participants: List[Participant]):
    try:
        session_data = session.to_dict()
        session_response = supabase.table("sessions").insert(session_data).execute()

        if not session_response.data:
            raise APIError({"message": "Failed to create session"})

        current_time = datetime.now().isoformat()
        session_users_data = [
            {
                "session_id": session.id,
                "user_id": get_or_create_users(participant.walletAddress),
                "last_update": current_time,
                "total_spent": 0,
                "joined": participant.joined,
            }
            for participant in participants
        ]

        session_users_response = (
            supabase.table("sessions_users").insert(session_users_data).execute()
        )

        if not session_users_response.data:
            supabase.table("sessions").delete().eq("id", session.id).execute()
            raise APIError({"message": "Failed to add users to session"})

        return session
    except APIError:
        raise


def get_sessions_by_wallet_address(walletAddress: str):
    try:
        user = (
            supabase.table("users")
            .select("id")
            .eq("walletAddress", walletAddress)
            .single()
            .execute()
        )
        if not user.data:
            raise ValueError("User not found")

        user_id = user.data["id"]

        sessions = (
            supabase.table("sessions_users")
            .select("session_id,joined, sessions(*)")
            .eq("user_id", user_id)
            .execute()
        )
        formatted_sessions = []
        for item in sessions.data:
            session_info = item["sessions"]
            session_info["id"] = item["session_id"]
            session_info["is_joined"] = item["joined"]
            formatted_sessions.append(session_info)

        return formatted_sessions
    except Exception as e:
        raise Exception(f"Error getting sessions: {str(e)}")


def join_session(session_id: int, wallet_address: str):
    try:
        user = (
            supabase.table("users")
            .select("id")
            .eq("walletAddress", wallet_address)
            .single()
            .execute()
        )
        if not user.data:
            raise ValueError("User not found")
        user_id = user.data["id"]

        session = (
            supabase.table("sessions")
            .select("id")
            .eq("id", session_id)
            .single()
            .execute()
        )
        if not session.data:
            raise ValueError("Session not found")

        existing_entry = (
            supabase.table("sessions_users")
            .select("*")
            .eq("session_id", session_id)
            .eq("user_id", user_id)
            .single()
            .execute()
        )
        if existing_entry.data:
            if existing_entry.data["joined"]:
                raise ValueError("User is already joined to this session")

            updated = (
                supabase.table("sessions_users")
                .update({"joined": True})
                .eq("session_id", session_id)
                .eq("user_id", user_id)
                .execute()
            )
        else:
            current_time = datetime.now().isoformat()
            new_entry = {
                "session_id": session_id,
                "user_id": user_id,
                "joined": True,
                "last_update": current_time,
                "total_spent": 0,
            }
            updated = supabase.table("sessions_users").insert(new_entry).execute()

        if not updated.data:
            raise ValueError("Failed to update session_users")

        return updated.data[0]
    except Exception as e:
        raise Exception(f"Error joining session: {str(e)}")


def activate_session(session_id: int, wallet_address: str):
    try:
        session = (
            supabase.table("sessions")
            .select("*")
            .eq("id", session_id)
            .single()
            .execute()
        )
        if not session.data:
            raise ValueError("Session not found")

        if session.data["state"] == "Active":
            return session.data

        session_users = (
            supabase.table("sessions_users")
            .select("*,user:users(walletAddress)")
            .eq("session_id", session_id)
            .execute()
        )

        if not session_users.data:
            raise ValueError("No participants found for this session")

        user_in_session = any(
            user["user"]["walletAddress"] == wallet_address
            for user in session_users.data
        )
        if not user_in_session:
            raise ValueError("User is not a participant in this session")

        all_joined = all(user["joined"] for user in session_users.data)
        if not all_joined:
            raise ValueError("Not all participants have joined the session yet")

        updated = (
            supabase.table("sessions")
            .update({"state": "Active"})
            .eq("id", session_id)
            .execute()
        )

        if not updated.data:
            raise ValueError("Failed to activate session")

        return updated.data[0]
    except Exception as e:
        raise Exception(f"Error activating session: {str(e)}")


def get_session_details(session_id: int):
    try:
        session = (
            supabase.table("sessions")
            .select("*")
            .eq("id", session_id)
            .single()
            .execute()
        )
        if not session.data:
            raise ValueError("Session not found")

        participants = (
            supabase.table("sessions_users")
            .select("user_id, joined, total_spent, users(id, name, walletAddress)")
            .eq("session_id", session_id)
            .execute()
        )

        expenses = (
            supabase.table("expenses")
            .select("id, user_id, amount, description, date")
            .eq("session_id", session_id)
            .execute()
        )

        formatted_participants = [
            {
                "id": p["users"]["id"],
                "name": p["users"]["name"],
                "walletAddress": p["users"]["walletAddress"],
                "joined": p["joined"],
                "total_spent": p["total_spent"],
            }
            for p in participants.data
        ]

        formatted_expenses = [
            {
                "id": e["id"],
                "user_id": e["user_id"],
                "amount": e["amount"],
                "description": e["description"],
                "date": (
                    e["date"].isoformat()
                    if isinstance(e["date"], datetime)
                    else e["date"]
                ),
            }
            for e in expenses.data
        ]

        return {
            "session": session.data,
            "participants": formatted_participants,
            "expenses": formatted_expenses,
        }

    except Exception as e:
        raise Exception(f"Error getting session details: {str(e)}")
