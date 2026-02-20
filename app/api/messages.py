from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from typing import List, Optional
from pydantic import BaseModel
from datetime import datetime
import json
import asyncio

from app.services.database import get_db
from app.api.deps import get_current_user, require_admin
from app.config import settings

router = APIRouter(prefix="/api/messages", tags=["messages"])

# =========================================================
# Pydantic Models
# =========================================================

class MessageBase(BaseModel):
    content: str
    conversation_id: int

class MessageCreate(MessageBase):
    pass

class MessageResponse(MessageBase):
    id: int
    sender_id: int
    created_at: datetime
    is_read: bool

class ConversationBase(BaseModel):
    participant_ids: List[int]
    title: Optional[str] = None
    is_broadcast: bool = False

class ConversationCreate(ConversationBase):
    pass

class ConversationResponse(ConversationBase):
    id: int
    created_at: datetime
    last_message_at: Optional[datetime]
    unread_count: int = 0
    participants: List[dict]
    last_message: Optional[dict]
    is_broadcast: bool = False

class UnreadCountResponse(BaseModel):
    total_unread: int
    conversations: List[dict]

class BroadcastMessage(BaseModel):
    content: str
    title: Optional[str] = "Announcement"

# =========================================================
# Database Functions
# =========================================================

def is_user_admin(conn, user_id: int) -> bool:
    """Check if a user is an admin"""
    cur = conn.cursor()
    cur.execute("""
        SELECT is_admin FROM auth.users WHERE id = %s
    """, (user_id,))
    result = cur.fetchone()
    return result and result[0] is True

def get_all_admins(conn, current_user_id: int) -> List[dict]:
    """Get all admin users for regular users to choose from"""
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            id,
            email,
            email as username,
            is_admin
        FROM auth.users
        WHERE is_admin = TRUE
        AND id != %s
        ORDER BY email
    """, (current_user_id,))
    
    rows = cur.fetchall()
    return [
        {"id": row[0], "email": row[1], "username": row[2], "is_admin": row[3]}
        for row in rows
    ]

def get_all_non_admin_users(conn, admin_id: int) -> List[dict]:
    """Get all non-admin users for admin to choose from"""
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            id,
            email,
            email as username,
            is_admin
        FROM auth.users
        WHERE is_admin = FALSE
        ORDER BY email
    """)
    
    rows = cur.fetchall()
    return [
        {"id": row[0], "email": row[1], "username": row[2], "is_admin": row[3]}
        for row in rows
    ]

def create_conversation(conn, participant_ids: List[int], title: Optional[str] = None, is_broadcast: bool = False) -> int:
    """Create a new conversation between participants or return existing one"""
    cur = conn.cursor()
    
    # Sort participant IDs for consistent checking
    participant_ids.sort()
    
    # Check if conversation already exists between these participants
    # For 2-person conversations
    if len(participant_ids) == 2:
        cur.execute("""
            SELECT c.id
            FROM conversations c
            JOIN conversation_participants cp1 ON c.id = cp1.conversation_id
            JOIN conversation_participants cp2 ON c.id = cp2.conversation_id
            WHERE cp1.user_id = %s AND cp2.user_id = %s
            AND c.is_broadcast = FALSE
            AND (
                SELECT COUNT(*) FROM conversation_participants WHERE conversation_id = c.id
            ) = 2
        """, (participant_ids[0], participant_ids[1]))
        
        existing = cur.fetchone()
        if existing:
            print(f"Found existing conversation {existing[0]} between users {participant_ids}")
            return existing[0]
    
    # Create new conversation if none exists
    cur.execute("""
        INSERT INTO conversations (title, created_at, is_broadcast)
        VALUES (%s, NOW(), %s)
        RETURNING id
    """, (title, is_broadcast))
    
    conversation_id = cur.fetchone()[0]
    
    # Add participants
    for user_id in participant_ids:
        cur.execute("""
            INSERT INTO conversation_participants (conversation_id, user_id)
            VALUES (%s, %s)
        """, (conversation_id, user_id))
    
    conn.commit()
    print(f"Created new conversation {conversation_id} between users {participant_ids}")
    return conversation_id

def create_broadcast_conversations(conn, admin_id: int, user_ids: List[int], title: str) -> List[int]:
    """Create individual conversations between admin and each user"""
    conversation_ids = []
    
    for user_id in user_ids:
        # Use the updated create_conversation which now checks for existing conversations
        conv_id = create_conversation(conn, [admin_id, user_id], f"Chat with User {user_id}", False)
        conversation_ids.append(conv_id)
        print(f"Using conversation {conv_id} for admin {admin_id} and user {user_id}")
    
    return conversation_ids

def get_user_conversations(conn, user_id: int, is_admin: bool = False) -> List[dict]:
    """Get all conversations for a user with last message and unread count"""
    cur = conn.cursor()
    
    # Base query that always filters by user_id
    base_query = """
        SELECT 
            c.id,
            c.title,
            c.created_at,
            c.last_message_at,
            c.is_broadcast,
            (
                SELECT COUNT(*)
                FROM messages m
                WHERE m.conversation_id = c.id
                AND m.is_read = FALSE
                AND m.sender_id != %s
            ) as unread_count,
            (
                SELECT row_to_json(msg)
                FROM (
                    SELECT 
                        m.id,
                        m.conversation_id,
                        m.sender_id,
                        m.content,
                        m.created_at,
                        m.is_read
                    FROM messages m
                    WHERE m.conversation_id = c.id
                    ORDER BY m.created_at DESC
                    LIMIT 1
                ) msg
            ) as last_message
        FROM conversations c
        JOIN conversation_participants cp ON c.id = cp.conversation_id
        WHERE cp.user_id = %s
    """
    
    # All users see conversations they're part of - broadcasts and direct messages
    query = base_query + """
        AND (
            c.is_broadcast = TRUE
            OR (
                SELECT COUNT(*) FROM conversation_participants WHERE conversation_id = c.id
            ) = 2
        )
        ORDER BY c.last_message_at DESC NULLS LAST, c.created_at DESC
    """
    cur.execute(query, (user_id, user_id))
    
    rows = cur.fetchall()
    conversations = []
    
    for row in rows:
        # Get participants for this conversation
        cur.execute("""
            SELECT 
                u.id,
                u.email,
                u.email as username,
                u.is_admin
            FROM auth.users u
            JOIN conversation_participants cp ON u.id = cp.user_id
            WHERE cp.conversation_id = %s
        """, (row[0],))
        
        participants = [
            {
                "id": p[0], 
                "email": p[1], 
                "username": p[2],
                "is_admin": p[3]
            }
            for p in cur.fetchall()
        ]
        
        # Format the conversation
        conversation = {
            "id": row[0],
            "title": row[1],
            "created_at": row[2].isoformat() if isinstance(row[2], datetime) else row[2],
            "last_message_at": row[3].isoformat() if isinstance(row[3], datetime) else row[3],
            "is_broadcast": row[4],
            "unread_count": row[5] or 0,
            "last_message": row[6],
            "participants": participants
        }
        
        # Use email as title for better identification
        if not row[4]:  # if not broadcast
            other_participants = [p for p in participants if p["id"] != user_id]
            if other_participants:
                conversation["title"] = other_participants[0]["email"]
        
        conversations.append(conversation)
    
    print(f"Found {len(conversations)} conversations for user {user_id}")
    return conversations

def get_conversation_messages(conn, conversation_id: int, user_id: int, limit: int = 50, offset: int = 0) -> List[dict]:
    """Get messages for a conversation"""
    cur = conn.cursor()
    
    # Verify user is participant
    cur.execute("""
        SELECT 1 FROM conversation_participants
        WHERE conversation_id = %s AND user_id = %s
    """, (conversation_id, user_id))
    
    if not cur.fetchone():
        return None
    
    # Get messages
    cur.execute("""
        SELECT 
            id,
            conversation_id,
            sender_id,
            content,
            created_at,
            is_read
        FROM messages
        WHERE conversation_id = %s
        ORDER BY created_at DESC
        LIMIT %s OFFSET %s
    """, (conversation_id, limit, offset))
    
    rows = cur.fetchall()
    messages = []
    
    for row in rows:
        created_at = row[4]
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
            
        messages.append({
            "id": row[0],
            "conversation_id": row[1],
            "sender_id": row[2],
            "content": row[3],
            "created_at": created_at,
            "is_read": row[5]
        })
    
    return messages

def send_message(conn, conversation_id: int, sender_id: int, content: str) -> dict:
    """Send a new message"""
    cur = conn.cursor()
    
    # Verify user is participant
    cur.execute("""
        SELECT 1 FROM conversation_participants
        WHERE conversation_id = %s AND user_id = %s
    """, (conversation_id, sender_id))
    
    if not cur.fetchone():
        raise HTTPException(status_code=403, detail="Not a participant in this conversation")
    
    # Insert message
    cur.execute("""
        INSERT INTO messages (conversation_id, sender_id, content, created_at, is_read)
        VALUES (%s, %s, %s, NOW(), FALSE)
        RETURNING id, conversation_id, sender_id, content, created_at, is_read
    """, (conversation_id, sender_id, content))
    
    message = cur.fetchone()
    
    # Update conversation's last_message_at
    cur.execute("""
        UPDATE conversations
        SET last_message_at = NOW()
        WHERE id = %s
    """, (conversation_id,))
    
    conn.commit()
    
    # Get sender info
    cur.execute("""
        SELECT email, email as username, is_admin
        FROM auth.users
        WHERE id = %s
    """, (sender_id,))
    sender = cur.fetchone()
    
    # Convert datetime to ISO format string for JSON serialization
    created_at = message[4]
    if isinstance(created_at, datetime):
        created_at = created_at.isoformat()
    
    message_data = {
        "id": message[0],
        "conversation_id": message[1],
        "sender_id": message[2],
        "content": message[3],
        "created_at": created_at,
        "is_read": message[5],
        "sender": {
            "id": sender_id,
            "email": sender[0] if sender else None,
            "username": sender[1] if sender else None,
            "is_admin": sender[2] if sender else False
        } if sender else None
    }
    
    print(f"Message created: {message_data['id']} in conversation {conversation_id}")
    return message_data

def get_all_users_for_broadcast(conn, admin_id: int) -> List[dict]:
    """Get all non-admin users for broadcasting"""
    cur = conn.cursor()
    cur.execute("""
        SELECT id, email
        FROM auth.users
        WHERE is_admin = FALSE
        ORDER BY email
    """)
    
    rows = cur.fetchall()
    users = [
        {
            "id": row[0], 
            "email": row[1], 
            "username": row[1]
        }
        for row in rows
    ]
    print(f"Found {len(users)} users for broadcast")
    return users

def get_unread_counts(conn, user_id: int) -> dict:
    """Get unread message counts for user"""
    cur = conn.cursor()
    
    cur.execute("""
        SELECT 
            c.id,
            COUNT(m.id) as unread_count
        FROM conversations c
        JOIN conversation_participants cp ON c.id = cp.conversation_id
        LEFT JOIN messages m ON c.id = m.conversation_id 
            AND m.is_read = FALSE 
            AND m.sender_id != %s
        WHERE cp.user_id = %s
        GROUP BY c.id
    """, (user_id, user_id))
    
    rows = cur.fetchall()
    
    total_unread = sum(row[1] for row in rows)
    conversations = [{"conversation_id": row[0], "unread_count": row[1]} for row in rows]
    
    return {
        "total_unread": total_unread,
        "conversations": conversations
    }

# =========================================================
# API Endpoints
# =========================================================

@router.post("/conversations", response_model=dict)
async def create_conversation_endpoint(
    conversation: ConversationCreate,
    conn = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Create a new conversation"""
    try:
        is_admin = is_user_admin(conn, current_user["id"])
        
        # Regular users can only create conversations with admins
        if not is_admin:
            # Check if all participants are admins
            for pid in conversation.participant_ids:
                if not is_user_admin(conn, pid):
                    raise HTTPException(
                        status_code=403, 
                        detail="Regular users can only message admins"
                    )
        
        # Ensure current user is included in participants
        if current_user["id"] not in conversation.participant_ids:
            conversation.participant_ids.append(current_user["id"])
        
        conversation_id = create_conversation(
            conn, 
            conversation.participant_ids, 
            conversation.title,
            conversation.is_broadcast
        )
        
        return {
            "success": True,
            "conversation_id": conversation_id,
            "message": "Conversation created successfully"
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/conversations", response_model=List[dict])
async def get_conversations(
    conn = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get all conversations for current user"""
    try:
        is_admin = is_user_admin(conn, current_user["id"])
        conversations = get_user_conversations(conn, current_user["id"], is_admin)
        return conversations
    except Exception as e:
        print(f"Error getting conversations: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/conversations/{conversation_id}/messages")
async def get_messages(
    conversation_id: int,
    limit: int = 50,
    offset: int = 0,
    conn = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get messages for a conversation"""
    try:
        messages = get_conversation_messages(conn, conversation_id, current_user["id"], limit, offset)
        
        if messages is None:
            raise HTTPException(status_code=403, detail="Not a participant in this conversation")
        
        return messages
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/conversations/{conversation_id}/messages")
async def send_message_endpoint(
    conversation_id: int,
    message: MessageCreate,
    conn = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Send a message in a conversation"""
    try:
        new_message = send_message(conn, conversation_id, current_user["id"], message.content)
        return new_message
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/unread")
async def get_unread(
    conn = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get unread message counts"""
    try:
        counts = get_unread_counts(conn, current_user["id"])
        return counts
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/conversations/{conversation_id}/read")
async def mark_read(
    conversation_id: int,
    conn = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Mark all messages in a conversation as read"""
    try:
        # Mark messages as read in database
        cur = conn.cursor()
        cur.execute("""
            UPDATE messages
            SET is_read = TRUE
            WHERE conversation_id = %s
            AND sender_id != %s
            AND is_read = FALSE
        """, (conversation_id, current_user["id"]))
        
        conn.commit()
        
        return {"success": True, "marked_read": cur.rowcount}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/users/available")
async def get_available_users(
    conn = Depends(get_db),
    current_user: dict = Depends(get_current_user)
):
    """Get available users to start a conversation with"""
    try:
        is_admin = is_user_admin(conn, current_user["id"])
        
        if is_admin:
            # Admin sees all non-admin users
            users = get_all_non_admin_users(conn, current_user["id"])
        else:
            # Regular users see all admins
            users = get_all_admins(conn, current_user["id"])
        
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
# Admin Broadcast Endpoints
# =========================================================

@router.post("/admin/broadcast", response_model=dict)
async def broadcast_message(
    broadcast: BroadcastMessage,
    background_tasks: BackgroundTasks,
    conn = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Admin can broadcast a message to all users"""
    try:
        print(f"Broadcast started by admin {admin['id']}")
        
        # Get all non-admin users
        users = get_all_users_for_broadcast(conn, admin["id"])
        
        if not users:
            print("No users to broadcast to")
            return {
                "success": True,
                "message": "No users to broadcast to",
                "sent_count": 0
            }
        
        print(f"Found {len(users)} users to broadcast to")
        
        # Create or get conversations with each user
        user_ids = [u["id"] for u in users]
        conversation_ids = create_broadcast_conversations(
            conn, 
            admin["id"], 
            user_ids, 
            broadcast.title or "Announcement"
        )
        
        print(f"Created/retrieved {len(conversation_ids)} conversations for broadcast")
        
        # Send message to each conversation
        sent_count = 0
        for conv_id in conversation_ids:
            try:
                message = send_message(conn, conv_id, admin["id"], broadcast.content)
                print(f"Broadcast message sent to conversation {conv_id}, message ID: {message['id']}")
                sent_count += 1
            except Exception as e:
                print(f"Failed to send broadcast to conversation {conv_id}: {e}")
                continue
        
        print(f"Broadcast complete: {sent_count} messages sent")
        
        return {
            "success": True,
            "message": f"Broadcast sent to {sent_count} users",
            "sent_count": sent_count
        }
        
    except Exception as e:
        print(f"Broadcast error: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/admin/users")
async def get_all_users_for_admin(
    conn = Depends(get_db),
    admin: dict = Depends(require_admin)
):
    """Admin can get list of all non-admin users"""
    try:
        users = get_all_users_for_broadcast(conn, admin["id"])
        return users
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =========================================================
# WebSocket for real-time messaging
# =========================================================

class ConnectionManager:
    def __init__(self):
        self.active_connections: dict[int, List[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, websocket: WebSocket, conversation_id: int):
        async with self._lock:
            if conversation_id not in self.active_connections:
                self.active_connections[conversation_id] = []
            self.active_connections[conversation_id].append(websocket)
            print(f"Total connections for conversation {conversation_id}: {len(self.active_connections[conversation_id])}")

    def disconnect(self, websocket: WebSocket, conversation_id: int):
        if conversation_id in self.active_connections:
            if websocket in self.active_connections[conversation_id]:
                self.active_connections[conversation_id].remove(websocket)
                print(f"Removed connection from conversation {conversation_id}")
            if not self.active_connections[conversation_id]:
                del self.active_connections[conversation_id]
                print(f"No more connections for conversation {conversation_id}")

    async def send_message(self, message: dict, conversation_id: int):
        if conversation_id in self.active_connections:
            disconnected = []
            for connection in self.active_connections[conversation_id]:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    print(f"Error sending message to connection: {e}")
                    disconnected.append(connection)
            
            for conn in disconnected:
                self.disconnect(conn, conversation_id)

manager = ConnectionManager()

@router.websocket("/ws/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket,
    conversation_id: int,
    conn = Depends(get_db)
):
    """WebSocket endpoint for real-time messaging using cookie authentication"""
    print(f"WebSocket connection attempt for conversation {conversation_id}")
    
    await websocket.accept()
    print(f"WebSocket accepted for conversation {conversation_id}")
    
    try:
        cookies = websocket.cookies
        session_cookie = cookies.get("access_token")
        
        if not session_cookie:
            print(f"No session cookie found for conversation {conversation_id}")
            await websocket.close(code=1008, reason="No session cookie")
            return
        
        print(f"Session cookie found for conversation {conversation_id}")
        
        from app.utils.security import decode_access_token
        try:
            payload = decode_access_token(session_cookie)
            email = payload.get("sub")
            
            if not email:
                print(f"Invalid token payload for conversation {conversation_id}")
                await websocket.close(code=1008, reason="Invalid session")
                return
                
            print(f"User authenticated with email: {email}")
        except Exception as e:
            print(f"Token decode error for conversation {conversation_id}: {e}")
            await websocket.close(code=1008, reason="Invalid session")
            return
        
        cur = conn.cursor()
        cur.execute("""
            SELECT id FROM auth.users WHERE email = %s
        """, (email,))
        
        user_row = cur.fetchone()
        if not user_row:
            print(f"User not found for email: {email}")
            await websocket.close(code=1008, reason="User not found")
            return
            
        user_id = user_row[0]
        print(f"Found user ID: {user_id} for email: {email}")
        
        cur.execute("""
            SELECT 1 FROM conversation_participants
            WHERE conversation_id = %s AND user_id = %s
        """, (conversation_id, user_id))
        
        if not cur.fetchone():
            print(f"User {user_id} not a participant in conversation {conversation_id}")
            await websocket.close(code=1008, reason="Not a participant")
            return
        
        print(f"User {user_id} verified as participant in conversation {conversation_id}")
        
        await manager.connect(websocket, conversation_id)
        print(f"WebSocket connected for user {user_id} in conversation {conversation_id}")
        
        await websocket.send_json({"type": "connected", "message": "Connected to conversation"})
        
        try:
            while True:
                try:
                    data = await asyncio.wait_for(websocket.receive_text(), timeout=30)
                    print(f"Received message in conversation {conversation_id}")
                    
                    message_data = json.loads(data)
                    
                    new_message = send_message(
                        conn, 
                        conversation_id, 
                        user_id, 
                        message_data["content"]
                    )
                    
                    print(f"Message saved to database with ID: {new_message['id']}")
                    
                    await manager.send_message(new_message, conversation_id)
                    print(f"Message broadcast to conversation {conversation_id}")
                    
                except asyncio.TimeoutError:
                    try:
                        await websocket.send_json({"type": "ping"})
                    except:
                        break
                        
        except WebSocketDisconnect:
            print(f"WebSocket disconnected for conversation {conversation_id}")
            manager.disconnect(websocket, conversation_id)
            
    except Exception as e:
        print(f"WebSocket error in conversation {conversation_id}: {e}")
        import traceback
        traceback.print_exc()
        try:
            await websocket.close(code=1011)
        except:
            pass