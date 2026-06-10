from typing import List, Dict, Any, Optional
import json
import sys
from datetime import datetime
from fastmcp import FastMCP

# MCP-UI SDK is currently only available for TypeScript/Node.js and Ruby
# Python implementation doesn't exist yet, so we'll use HTML-based MCP resources
from whatsapp import (
    search_contacts as whatsapp_search_contacts,
    list_messages as whatsapp_list_messages,
    list_chats as whatsapp_list_chats,
    get_chat as whatsapp_get_chat,
    get_direct_chat_by_contact as whatsapp_get_direct_chat_by_contact,
    get_contact_chats as whatsapp_get_contact_chats,
    get_last_interaction as whatsapp_get_last_interaction,
    get_message_context as whatsapp_get_message_context,
    send_message as whatsapp_send_message,
    send_reply as whatsapp_send_reply,
    send_file as whatsapp_send_file,
    send_audio_message as whatsapp_audio_voice_message,
    download_media as whatsapp_download_media,
    ensure_bridge_ready,
    get_bridge_status,
    MESSAGES_DB_PATH,
    schedule_message as whatsapp_schedule_message,
    list_scheduled_messages as whatsapp_list_scheduled_messages,
    cancel_scheduled_message as whatsapp_cancel_scheduled_message,
    watch_channel as whatsapp_watch_channel,
    unwatch_channel as whatsapp_unwatch_channel,
    list_watched_channels as whatsapp_list_watched_channels,
    archive_chat as whatsapp_archive_chat,
    resync_app_state as whatsapp_resync_app_state,
    get_group_info as whatsapp_get_group_info,
    add_group_members as whatsapp_add_group_members,
    remove_group_members as whatsapp_remove_group_members
)
import sqlite3
import os

# Initialize FastMCP server
mcp = FastMCP("whatsapp")

def with_bridge_check(func):
    """Decorator to ensure bridge is ready before executing MCP tools."""
    import functools

    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        # Check bridge readiness
        success, message, qr_url = ensure_bridge_ready()

        if not success:
            if qr_url:
                # Return QR URL for authentication
                return {
                    "error": "WhatsApp Authentication Required",
                    "message": message,
                    "qr_url": qr_url,
                    "instructions": [
                        "1. Open the QR code page in your browser:",
                        f"   {qr_url}",
                        "2. Open WhatsApp on your phone",
                        "3. Go to Settings > Linked Devices",
                        "4. Tap 'Link a Device'",
                        "5. Scan the QR code displayed on the web page",
                        "6. Wait for authentication to complete",
                        "7. Try your request again"
                    ]
                }
            else:
                # Return error message
                return {
                    "error": "WhatsApp Bridge Error",
                    "message": message,
                    "troubleshooting": [
                        "Ensure Go is installed on your system",
                        "Check that the bridge directory exists",
                        "Verify network connectivity",
                        "Try restarting the MCP server"
                    ]
                }

        # Bridge is ready, execute the original function
        try:
            return func(*args, **kwargs)
        except Exception as e:
            return {
                "error": "Tool Execution Error",
                "message": str(e),
                "suggestion": "Please try again or check the bridge status"
            }

    return wrapper

@mcp.tool()
@with_bridge_check
def search_contacts(query: str) -> List[Dict[str, Any]]:
    """Search WhatsApp contacts by name or phone number.

    Args:
        query: Search term to match against contact names or phone numbers
    """
    contacts = whatsapp_search_contacts(query)
    return contacts

@mcp.tool()
@with_bridge_check
def list_messages(
    after: Optional[str] = None,
    before: Optional[str] = None,
    sender_phone_number: Optional[str] = None,
    chat_jid: Optional[str] = None,
    query: Optional[str] = None,
    limit: int = 20,
    page: int = 0,
    include_context: bool = True,
    context_before: int = 1,
    context_after: int = 1
) -> List[Dict[str, Any]]:
    """Get WhatsApp messages matching specified criteria with optional context.

    Args:
        after: Optional ISO-8601 formatted string to only return messages after this date
        before: Optional ISO-8601 formatted string to only return messages before this date
        sender_phone_number: Optional phone number to filter messages by sender
        chat_jid: Optional chat JID to filter messages by chat
        query: Optional search term to filter messages by content
        limit: Maximum number of messages to return (default 20)
        page: Page number for pagination (default 0)
        include_context: Whether to include messages before and after matches (default True)
        context_before: Number of messages to include before each match (default 1)
        context_after: Number of messages to include after each match (default 1)
    """
    messages = whatsapp_list_messages(
        after=after,
        before=before,
        sender_phone_number=sender_phone_number,
        chat_jid=chat_jid,
        query=query,
        limit=limit,
        page=page,
        include_context=include_context,
        context_before=context_before,
        context_after=context_after
    )
    return messages

@mcp.tool()
@with_bridge_check
def list_chats(
    query: Optional[str] = None,
    limit: int = 20,
    page: int = 0,
    include_last_message: bool = True,
    sort_by: str = "last_active",
    archived: Optional[bool] = None
) -> List[Dict[str, Any]]:
    """Get WhatsApp chats matching specified criteria.

    Args:
        query: Optional search term to filter chats by name or JID
        limit: Maximum number of chats to return (default 20)
        page: Page number for pagination (default 0)
        include_last_message: Whether to include the last message in each chat (default True)
        sort_by: Field to sort results by, either "last_active" or "name" (default "last_active")
        archived: Optional filter for archived status. None returns all chats (default), True returns only archived chats, False returns only unarchived chats (inbox)
    """
    chats = whatsapp_list_chats(
        query=query,
        limit=limit,
        page=page,
        include_last_message=include_last_message,
        sort_by=sort_by,
        archived=archived
    )
    return chats

@mcp.tool()
@with_bridge_check
def get_chat(chat_jid: str, include_last_message: bool = True) -> Dict[str, Any]:
    """Get WhatsApp chat metadata by JID.

    Args:
        chat_jid: The JID of the chat to retrieve
        include_last_message: Whether to include the last message (default True)
    """
    chat = whatsapp_get_chat(chat_jid, include_last_message)
    return chat

@mcp.tool()
@with_bridge_check
def get_direct_chat_by_contact(sender_phone_number: str) -> Dict[str, Any]:
    """Get WhatsApp chat metadata by sender phone number.

    Args:
        sender_phone_number: The phone number to search for
    """
    chat = whatsapp_get_direct_chat_by_contact(sender_phone_number)
    return chat

@mcp.tool()
@with_bridge_check
def get_contact_chats(jid: str, limit: int = 20, page: int = 0) -> List[Dict[str, Any]]:
    """Get all WhatsApp chats involving the contact.

    Args:
        jid: The contact's JID to search for
        limit: Maximum number of chats to return (default 20)
        page: Page number for pagination (default 0)
    """
    chats = whatsapp_get_contact_chats(jid, limit, page)
    return chats

@mcp.tool()
@with_bridge_check
def get_last_interaction(jid: str) -> str:
    """Get most recent WhatsApp message involving the contact.

    Args:
        jid: The JID of the contact to search for
    """
    message = whatsapp_get_last_interaction(jid)
    return message

@mcp.tool()
@with_bridge_check
def get_message_context(
    message_id: str,
    before: int = 5,
    after: int = 5
) -> Dict[str, Any]:
    """Get context around a specific WhatsApp message.

    Args:
        message_id: The ID of the message to get context for
        before: Number of messages to include before the target message (default 5)
        after: Number of messages to include after the target message (default 5)
    """
    context = whatsapp_get_message_context(message_id, before, after)
    return context

@mcp.tool()
@with_bridge_check
def send_message(
    recipient: str,
    message: str
) -> Dict[str, Any]:
    """Send a WhatsApp message to a person or group. For group chats use the JID.

    Args:
        recipient: The recipient - either a phone number with country code but no + or other symbols,
                 or a JID (e.g., "123456789@s.whatsapp.net" or a group JID like "123456789@g.us")
        message: The message text to send

    Returns:
        A dictionary containing success status and a status message
    """
    # Validate input
    if not recipient:
        return {
            "success": False,
            "message": "Recipient must be provided"
        }

    # Call the whatsapp_send_message function with the unified recipient parameter
    success, status_message = whatsapp_send_message(recipient, message)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
@with_bridge_check
def send_reply(
    recipient: str,
    message: str,
    reply_to_id: str,
    reply_to_jid: str
) -> Dict[str, Any]:
    """Send a WhatsApp message as a reply to a specific message.

    Args:
        recipient: The recipient - either a phone number with country code but no + or other symbols,
                 or a JID (e.g., "123456789@s.whatsapp.net" or a group JID like "123456789@g.us")
        message: The message text to send
        reply_to_id: The ID of the message being replied to (from the message's 'id' field)
        reply_to_jid: The JID of the sender of the message being replied to (from the message's 'sender' field,
                     should be in format "123456789@s.whatsapp.net")

    Returns:
        A dictionary containing success status and a status message
    """
    # Validate input
    if not recipient:
        return {
            "success": False,
            "message": "Recipient must be provided"
        }

    if not reply_to_id:
        return {
            "success": False,
            "message": "reply_to_id must be provided"
        }

    # Call the whatsapp_send_reply function
    success, status_message = whatsapp_send_reply(recipient, message, reply_to_id, reply_to_jid)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
@with_bridge_check
def send_file(recipient: str, media_path: str = "", media_data: str = "", filename: str = "") -> Dict[str, Any]:
    """Send a file such as a picture, raw audio, video or document via WhatsApp to the specified recipient. For group messages use the JID.

    Supports multiple ways to provide the file:
    - media_data (preferred): Base64-encoded file data - use this for local files
    - media_path with URL: Remote URL (http:// or https://) to download and send
    - media_path with path: Container-accessible path (only works for mounted volumes)

    Args:
        recipient: The recipient - either a phone number with country code but no + or other symbols,
                 or a JID (e.g., "123456789@s.whatsapp.net" or a group JID like "123456789@g.us")
        media_path: Either a URL to download, or a container-accessible file path
        media_data: Base64-encoded file data (preferred for local files). Takes priority over media_path.
        filename: Original filename (required when using media_data, e.g., "image.png")

    Returns:
        A dictionary containing success status and a status message
    """

    # Call the whatsapp_send_file function
    success, status_message = whatsapp_send_file(recipient, media_path, media_data, filename)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
@with_bridge_check
def send_audio_message(recipient: str, media_path: str) -> Dict[str, Any]:
    """Send any audio file as a WhatsApp audio message to the specified recipient. For group messages use the JID. If it errors due to ffmpeg not being installed, use send_file instead.

    Supports both local file paths and remote URLs:
    - Local paths: Will be converted to Opus OGG format if needed (requires ffmpeg)
    - URLs (http:// or https://): File should already be in OGG Opus format for voice messages

    Args:
        recipient: The recipient - either a phone number with country code but no + or other symbols,
                 or a JID (e.g., "123456789@s.whatsapp.net" or a group JID like "123456789@g.us")
        media_path: Either an absolute path to the audio file, or a URL to download and send

    Returns:
        A dictionary containing success status and a status message
    """
    success, status_message = whatsapp_audio_voice_message(recipient, media_path)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
@with_bridge_check
def download_media(message_id: str, chat_jid: str) -> Dict[str, Any]:
    """Download media from a WhatsApp message and get the local file path.

    Args:
        message_id: The ID of the message containing the media
        chat_jid: The JID of the chat containing the message

    Returns:
        A dictionary containing success status, a status message, and the file path if successful
    """
    result = whatsapp_download_media(message_id, chat_jid)
    return result

@mcp.tool()
@with_bridge_check
def schedule_message(
    recipient: str,
    message: str,
    scheduled_time: str,
    media_path: Optional[str] = None
) -> Dict[str, Any]:
    """Schedule a WhatsApp message for future delivery.

    Args:
        recipient: The recipient - either a phone number with country code but no + or other symbols,
                 or a JID (e.g., "123456789@s.whatsapp.net" or a group JID like "123456789@g.us")
        message: The message text to send
        scheduled_time: When to send the message in ISO 8601 format (e.g., "2024-12-25T10:00:00Z")
        media_path: Optional absolute path to a media file to send with the message

    Returns:
        A dictionary containing success status, a status message, and the scheduled message ID
    """
    if not recipient:
        return {
            "success": False,
            "message": "Recipient must be provided"
        }

    if not message and not media_path:
        return {
            "success": False,
            "message": "Message or media_path must be provided"
        }

    success, status_message, message_id = whatsapp_schedule_message(
        recipient, message, scheduled_time, media_path
    )

    result = {
        "success": success,
        "message": status_message
    }
    if message_id:
        result["scheduled_message_id"] = message_id

    return result

@mcp.tool()
@with_bridge_check
def list_scheduled_messages(status: Optional[str] = None) -> Dict[str, Any]:
    """List all scheduled WhatsApp messages.

    Args:
        status: Optional filter by status - "pending", "sent", or "failed"

    Returns:
        A dictionary containing the list of scheduled messages and count
    """
    messages = whatsapp_list_scheduled_messages(status)
    return {
        "success": True,
        "messages": messages,
        "count": len(messages)
    }

@mcp.tool()
@with_bridge_check
def cancel_scheduled_message(message_id: int) -> Dict[str, Any]:
    """Cancel a pending scheduled WhatsApp message.

    Args:
        message_id: The ID of the scheduled message to cancel

    Returns:
        A dictionary containing success status and a status message
    """
    success, status_message = whatsapp_cancel_scheduled_message(message_id)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
@with_bridge_check
def watch_channel(jid: str, name: Optional[str] = None) -> Dict[str, Any]:
    """Add a WhatsApp channel/chat to the watch list. Messages from watched channels trigger webhooks to the configured WHATSAPP_WEBHOOK_URL.

    Args:
        jid: The JID of the channel to watch (e.g., "123456789@s.whatsapp.net" or group JID)
        name: Optional friendly name for the channel

    Returns:
        A dictionary containing success status and a status message
    """
    if not jid:
        return {
            "success": False,
            "message": "JID must be provided"
        }

    success, status_message = whatsapp_watch_channel(jid, name)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
@with_bridge_check
def unwatch_channel(jid: str) -> Dict[str, Any]:
    """Remove a WhatsApp channel/chat from the watch list.

    Args:
        jid: The JID of the channel to stop watching

    Returns:
        A dictionary containing success status and a status message
    """
    if not jid:
        return {
            "success": False,
            "message": "JID must be provided"
        }

    success, status_message = whatsapp_unwatch_channel(jid)
    return {
        "success": success,
        "message": status_message
    }

@mcp.tool()
@with_bridge_check
def list_watched_channels() -> Dict[str, Any]:
    """List all WhatsApp channels/chats being watched for webhook notifications.

    Returns:
        A dictionary containing the list of watched channels, count, and configured webhook URL
    """
    result = whatsapp_list_watched_channels()
    return {
        "success": True,
        "channels": result.get("channels", []),
        "count": result.get("count", 0),
        "webhook_url": result.get("webhook_url", "")
    }

@mcp.tool()
@with_bridge_check
def archive_chat(jid: str, archive: bool = True) -> Dict[str, Any]:
    """Archive or unarchive a WhatsApp chat. Archiving a chat will hide it from the main chat list. Note: Archiving a chat will also unpin it if it was pinned.

    Args:
        jid: The JID of the chat to archive/unarchive (e.g., "123456789@s.whatsapp.net" or group JID like "123456789@g.us")
        archive: True to archive the chat, False to unarchive (default True)

    Returns:
        A dictionary containing success status and a status message
    """
    if not jid:
        return {
            "success": False,
            "message": "JID must be provided"
        }

    success, status_message = whatsapp_archive_chat(jid, archive)
    return {
        "success": success,
        "message": status_message
    }


@mcp.tool()
@with_bridge_check
def resync_app_state(names: Optional[List[str]] = None, force: bool = False) -> Dict[str, Any]:
    """Force a full resync of WhatsApp app state to fix sync issues.

    Use this when archive, pin, mute, or star operations fail with 409 conflict or LTHash errors.
    The resync clears the local state cache and re-fetches all patches from WhatsApp servers.

    When operations still fail after a normal resync (e.g. "failed to verify snapshot:
    mismatching LTHash"), use force=True. This wipes the local app state snapshot from
    SQLite so WhatsApp sends a complete fresh snapshot, bypassing the corrupt LTHash check.

    Args:
        names: Optional list of specific state names to resync.
               Valid values: "regular_low" (archive/pin), "regular_high" (mute/star),
               "regular", "critical_block", "critical_unblock_low".
               If not provided, resyncs regular_low and regular_high (most common).
        force: If True, wipe local app state tables before fetching. Use when a normal
               resync still fails with LTHash mismatch on the snapshot itself. Default False.

    Returns:
        A dictionary containing success status and per-state resync results
    """
    return whatsapp_resync_app_state(names, force=force)


@mcp.tool()
@with_bridge_check
def get_group_info(group_jid: str) -> Dict[str, Any]:
    """Get information about a WhatsApp group including its members.

    Args:
        group_jid: The JID of the group (must end with @g.us, e.g., "123456789@g.us")

    Returns:
        A dictionary containing:
        - success: Whether the request succeeded
        - jid: The group JID
        - name: The group name
        - topic: The group description/topic
        - owner_jid: JID of the group owner
        - participants: List of group members with their JID, name, is_admin, and is_super_admin status
        - participant_count: Number of participants
    """
    if not group_jid:
        return {
            "success": False,
            "message": "group_jid must be provided"
        }

    if not group_jid.endswith("@g.us"):
        return {
            "success": False,
            "message": "group_jid must be a group JID (ending with @g.us)"
        }

    result = whatsapp_get_group_info(group_jid)
    return result


@mcp.tool()
@with_bridge_check
def add_group_member(group_jid: str, participant: str) -> Dict[str, Any]:
    """Add a contact to a WhatsApp group. You must be an admin of the group to add members.

    Args:
        group_jid: The JID of the group (must end with @g.us, e.g., "123456789@g.us")
        participant: The phone number (with country code, no + or symbols) or JID of the contact to add

    Returns:
        A dictionary containing success status, message, and results for the participant
    """
    if not group_jid:
        return {
            "success": False,
            "message": "group_jid must be provided"
        }

    if not group_jid.endswith("@g.us"):
        return {
            "success": False,
            "message": "group_jid must be a group JID (ending with @g.us)"
        }

    if not participant:
        return {
            "success": False,
            "message": "participant must be provided"
        }

    result = whatsapp_add_group_members(group_jid, [participant])
    return result


@mcp.tool()
@with_bridge_check
def remove_group_member(group_jid: str, participant: str) -> Dict[str, Any]:
    """Remove a contact from a WhatsApp group. You must be an admin of the group to remove members.

    Args:
        group_jid: The JID of the group (must end with @g.us, e.g., "123456789@g.us")
        participant: The phone number (with country code, no + or symbols) or JID of the contact to remove

    Returns:
        A dictionary containing success status, message, and results for the participant
    """
    if not group_jid:
        return {
            "success": False,
            "message": "group_jid must be provided"
        }

    if not group_jid.endswith("@g.us"):
        return {
            "success": False,
            "message": "group_jid must be a group JID (ending with @g.us)"
        }

    if not participant:
        return {
            "success": False,
            "message": "participant must be provided"
        }

    result = whatsapp_remove_group_members(group_jid, [participant])
    return result


@mcp.resource("whatsapp://sync-status")
def get_sync_status_resource() -> str:
    """Resource showing the current sync status and last activity."""
    try:
        # Get bridge status
        bridge_status = get_bridge_status()

        # Get database stats
        message_count = 0
        last_sync_time = None
        chat_count = 0

        if os.path.exists(MESSAGES_DB_PATH):
            conn = sqlite3.connect(MESSAGES_DB_PATH)
            cursor = conn.cursor()

            # Get message count
            cursor.execute("SELECT COUNT(*) FROM messages")
            message_count = cursor.fetchone()[0]

            # Get last message time as proxy for last sync
            cursor.execute("SELECT MAX(timestamp) FROM messages")
            last_sync_result = cursor.fetchone()[0]
            if last_sync_result:
                last_sync_time = datetime.fromisoformat(last_sync_result)

            # Get chat count
            cursor.execute("SELECT COUNT(*) FROM chats")
            chat_count = cursor.fetchone()[0]

            conn.close()

        # Format the status report
        status_report = {
            "timestamp": datetime.now().isoformat(),
            "bridge_status": {
                "running": bridge_status.is_running,
                "authenticated": bridge_status.is_authenticated,
                "api_responsive": bridge_status.api_responsive,
                "overall": "Ready" if (bridge_status.is_running and bridge_status.api_responsive and bridge_status.is_authenticated) else "Not Ready"
            },
            "sync_stats": {
                "total_messages": message_count,
                "total_chats": chat_count,
                "last_sync_time": last_sync_time.isoformat() if last_sync_time else None,
                "database_exists": os.path.exists(MESSAGES_DB_PATH)
            },
            "errors": bridge_status.error_message if bridge_status.error_message else None
        }

        return json.dumps(status_report, indent=2)

    except Exception as e:
        error_report = {
            "timestamp": datetime.now().isoformat(),
            "error": str(e),
            "status": "Error retrieving sync status"
        }
        return json.dumps(error_report, indent=2)

@mcp.tool()
@with_bridge_check
def get_sync_status() -> Dict[str, Any]:
    """Get comprehensive sync status including last sync time and statistics.

    Returns:
        A dictionary with sync status, timing, and database statistics
    """
    try:
        # Get bridge status
        bridge_status = get_bridge_status()

        # Get database stats and sync timing
        stats = {
            "message_count": 0,
            "chat_count": 0,
            "last_sync_time": None,
            "database_size_mb": 0,
            "database_exists": False
        }

        if os.path.exists(MESSAGES_DB_PATH):
            stats["database_exists"] = True
            stats["database_size_mb"] = round(os.path.getsize(MESSAGES_DB_PATH) / (1024 * 1024), 2)

            conn = sqlite3.connect(MESSAGES_DB_PATH)
            cursor = conn.cursor()

            # Get counts
            cursor.execute("SELECT COUNT(*) FROM messages")
            stats["message_count"] = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM chats")
            stats["chat_count"] = cursor.fetchone()[0]

            # Get last activity (most recent message timestamp)
            cursor.execute("SELECT MAX(timestamp) FROM messages")
            last_message = cursor.fetchone()[0]
            if last_message:
                stats["last_sync_time"] = last_message

            conn.close()

        return {
            "sync_status": "Active" if bridge_status.is_running and bridge_status.is_authenticated else "Inactive",
            "bridge_status": {
                "running": bridge_status.is_running,
                "authenticated": bridge_status.is_authenticated,
                "api_responsive": bridge_status.api_responsive
            },
            "statistics": stats,
            "last_check": datetime.now().isoformat(),
            "error": bridge_status.error_message
        }

    except Exception as e:
        return {
            "sync_status": "Error",
            "error": str(e),
            "last_check": datetime.now().isoformat()
        }

@mcp.tool()
@with_bridge_check
def check_bridge_status() -> Dict[str, Any]:
    """Check the current status of the WhatsApp bridge and authentication.

    Returns:
        A dictionary containing the bridge status, authentication state, and any error messages
    """
    status = get_bridge_status()

    return {
        "bridge_running": status.is_running,
        "api_responsive": status.api_responsive,
        "authenticated": status.is_authenticated,
        "status": "Ready" if (status.is_running and status.api_responsive and status.is_authenticated) else "Not Ready",
        "error_message": status.error_message,
        "details": {
            "bridge_process": "Running" if status.is_running else "Stopped",
            "api_server": "Responsive" if status.api_responsive else "Not responding",
            "whatsapp_auth": "Authenticated" if status.is_authenticated else "Not authenticated"
        }
    }

if __name__ == "__main__":
    # Get transport mode from environment variable
    # Default to 'stdio' for backward compatibility with local installations
    # Docker environments should set MCP_TRANSPORT=sse
    transport_mode = os.environ.get('MCP_TRANSPORT', 'stdio')

    # Validate transport mode
    valid_transports = ['stdio', 'sse']
    if transport_mode not in valid_transports:
        print(f"Warning: Invalid MCP_TRANSPORT '{transport_mode}', defaulting to 'stdio'", file=sys.stderr)
        transport_mode = 'stdio'

    print(f"Starting WhatsApp MCP server with {transport_mode} transport...", file=sys.stderr)

    # Initialize and run the server
    if transport_mode == 'sse':
        port = int(os.environ.get('MCP_PORT', 3000))
        print(f"SSE transport listening on port {port}", file=sys.stderr)
        try:
            import uvicorn
            uvicorn.run(mcp.sse_app(), host='0.0.0.0', port=port)
        except ImportError:
            mcp.run(transport=transport_mode, host="127.0.0.1", port=port)
    else:
        # For stdio transport, don't specify host/port
        mcp.run(transport=transport_mode)
