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
                    loading={loading}
                />
            </div>
        </div>
    );
};

export default ChatInterface;
