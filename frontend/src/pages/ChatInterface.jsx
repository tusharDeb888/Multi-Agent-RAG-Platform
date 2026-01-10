import React, { useState, useEffect } from 'react';
import { Trash2 } from 'lucide-react';
import ChatWindow from '../components/ChatWindow';
import chatService from '../services/chatService';
import storageService from '../services/storageService';
import authService from '../services/authService';

const ChatInterface = () => {
    const user = authService.getCurrentUser();

    // Initialize state from storage
    const [messages, setMessages] = useState(() => {
        return storageService.getItem('chat_session_messages') || [];
    });

    // Reset messages when user context changes
    useEffect(() => {
        const saved = storageService.getItem('chat_session_messages');
        setMessages(saved || []);
    }, [user?.id, user?.username]);

    const [loading, setLoading] = useState(false);

    // Save messages to storage whenever they change
    useEffect(() => {
        storageService.setItem('chat_session_messages', messages);
    }, [messages, user]);


    const handleSendMessage = async (text) => {
        // Add user message
        const userMessage = { role: 'user', content: text };
        setMessages((prev) => [...prev, userMessage]);

        // Add initial bot placeholder
        const botMessageId = Date.now();
        setMessages((prev) => [
            ...prev,
            {
                id: botMessageId,
                role: 'assistant',
                content: '',
                citations: [],
                isStreaming: true,
                status: 'Initializing...'
            }
        ]);
        setLoading(true);

        chatService.streamQuery(
            text,
            (chunk) => {
                setMessages((prev) => {
                    return prev.map((msg) => {
                        if (msg.id === botMessageId) {
                            if (chunk.status) {
                                return { ...msg, status: chunk.status };
                            }
                            if (chunk.token) {
                                return { ...msg, content: msg.content + chunk.token, status: 'Generating...' };
                            }
                            if (chunk.citations) {
                                return { ...msg, citations: chunk.citations };
                            }
                            if (chunk.error) {
                                return { ...msg, content: msg.content + "\n[Error: " + chunk.error + "]", isStreaming: false };
                            }
                        }
                        return msg;
                    });
                });
            },
            () => {
                setMessages((prev) =>
                    prev.map(msg => msg.id === botMessageId ? { ...msg, isStreaming: false, status: null } : msg)
                );
                setLoading(false);
            },
            (error) => {
                console.error('Failed to send message:', error);
                setMessages((prev) =>
                    prev.map(msg => msg.id === botMessageId ? { ...msg, content: "Sorry, I encountered an error. Please try again.", isStreaming: false, status: null } : msg)
                );
                setLoading(false);
            }
        );
    };

    const handleEditMessage = (index, newContent) => {
        // Keep messages before the edited one
        setMessages(prev => {
            const newHistory = prev.slice(0, index);
            return newHistory;
        });

        // Use a timeout to ensure state update has processed before adding new message
        // slightly hacky but ensures clean separation of the "Rewind" and "New Send"
        setTimeout(() => {
            handleSendMessage(newContent);
        }, 0);
    };

    const handleRegenerate = (index) => {
        // If regenerating a User message: Keep history up to that user message (inclusive), then re-run the *next* assistant response?
        // Actually, "Regenerate" usually means "Re-run the response to THIS user message".
        // So we need to ensure the user message is the last one in the history passed to the bot.
        // But our `handleSendMessage` appends the user message.

        // Strategy:
        // 1. If it's a User message: We want to re-trigger the bot response for THIS message.
        //    So we revert history to include THIS message, but remove any subsequent ones.
        //    Then we call the API directly (not handleSendMessage, because that adds the user msg again).
        //    Actually, simpler: Revert history to BEFORE this message, then call handleSendMessage with the SAME content.

        // 2. If it's an Assistant message: We want to replace THIS message with a new one.
        //    So we find the User message that prompted this (index - 1).
        //    Then we revert history to BEFORE that User message, and call handleSendMessage with its content.

        let targetUserMsgIndex = index;
        if (messages[index].role === 'assistant') {
            targetUserMsgIndex = index - 1;
        }

        if (targetUserMsgIndex < 0) return; // Should not happen

        const userMsgContent = messages[targetUserMsgIndex].content;

        // Rewind to before the user message
        setMessages(prev => prev.slice(0, targetUserMsgIndex));

        setTimeout(() => {
            handleSendMessage(userMsgContent);
        }, 0);
    };

    return (
        <div className="h-full flex flex-col">
            <div className="mb-6 flex justify-between items-center">
                <div>
                    <h1 className="text-2xl font-bold text-gray-900">Chat with Knowledge Base</h1>
                    <p className="text-gray-600">Ask questions and get answers from secure documents</p>
                </div>
            </div>

            <div className="flex-1">
                <ChatWindow
                    messages={messages}
                    onSendMessage={handleSendMessage}
                    onEditMessage={handleEditMessage}
                    onRegenerate={handleRegenerate}
                    loading={loading}
                />
            </div>
        </div>
    );
};

export default ChatInterface;
