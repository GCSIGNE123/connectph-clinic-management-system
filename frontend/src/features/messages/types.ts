export interface InternalMessage {
  id: string;
  senderId: string;
  senderName: string | null;
  recipientId: string;
  recipientName: string | null;
  body: string;
  readAt: string | null;
  createdAt: string;
}

export interface ConversationResponse {
  items: InternalMessage[];
  total: number;
  unreadCount: number;
}

export interface StaffDirectoryEntry {
  id: string;
  fullName: string;
  role: string;
}

export interface ConversationUnread {
  otherUserId: string;
  otherUserName: string | null;
  unreadCount: number;
  lastMessageAt: string;
}
