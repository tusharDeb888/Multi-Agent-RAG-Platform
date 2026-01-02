import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { MessageSquare, Calendar, Clock } from 'lucide-react';
import authService from '../services/authService';

const ChatHistory = () => {
    const [history, setHistory] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        fetchHistory();
    }, []);

    const fetchHistory = async () => {
        try {
            const token = authService.getToken();
            const response = await axios.get('http://localhost:8000/api/v1/chat/history', {
                headers: { Authorization: `Bearer ${token}` }
            });
            setHistory(response.data);
        } catch (err) {
            setError('Failed to load chat history');
            console.error(err);
        } finally {
            setLoading(false);
        }
    };

    const formatDate = (dateString) => {
        return new Date(dateString).toLocaleDateString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit'
        });
    };

    if (loading) {
        return (
            <div className="flex items-center justify-center h-full">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="text-center text-red-600 mt-8">
                <p>{error}</p>
            </div>
        );
    }

    return (
        <div className="max-w-4xl mx-auto">
            <h1 className="text-2xl font-bold mb-6 flex items-center">
                <Clock className="mr-2 h-6 w-6 text-blue-600" />
                Chat History
            </h1>

            <div className="space-y-4">
                {history.length === 0 ? (
                    <div className="text-center text-gray-500 py-8 bg-white rounded-lg shadow">
                        <MessageSquare className="mx-auto h-12 w-12 text-gray-300 mb-2" />
                        <p>No chat history found.</p>
                    </div>
                ) : (
                    history.map((item, index) => (
                        <div key={index} className="bg-white rounded-lg shadow-sm hover:shadow-md transition-shadow p-6 border border-gray-100">
                            <div className="flex justify-between items-start mb-2">
                                <p className="text-sm text-gray-500 flex items-center">
                                    <Calendar className="h-4 w-4 mr-1" />
                                    {formatDate(item.timestamp)}
                                </p>
                            </div>

                            <div className="mb-3">
                                <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-1">Query</h3>
                                <p className="text-gray-900 bg-gray-50 p-3 rounded-md">{item.query}</p>
                            </div>

                            {item.response_snippet && (
                                <div>
                                    <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider mb-1">Response</h3>
                                    <p className="text-gray-700 text-sm">{item.response_snippet}</p>
                                </div>
                            )}
                        </div>
                    ))
                )}
            </div>
        </div>
    );
};

export default ChatHistory;
