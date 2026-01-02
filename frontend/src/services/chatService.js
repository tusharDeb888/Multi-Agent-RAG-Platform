import api from './api';

const sendQuery = async (query, topK = 5) => {
    const response = await api.post('/chat/query', {
        query,
        top_k: topK,
    });
    return response.data;
};

const streamQuery = async (query, onChunk, onComplete, onError, topK = 5) => {
    try {
        const token = localStorage.getItem('token');
        const response = await fetch('http://localhost:8000/api/v1/chat/stream', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${token}`,
            },
            body: JSON.stringify({
                query,
                top_k: topK,
            }),
        });

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            buffer += chunk;

            const lines = buffer.split('\n\n');
            buffer = lines.pop(); // Keep the last incomplete line in the buffer

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const dataStr = line.replace('data: ', '');
                    if (dataStr === '[DONE]') {
                        onComplete();
                        return;
                    }
                    try {
                        const data = JSON.parse(dataStr);
                        onChunk(data);
                    } catch (e) {
                        console.error('Error parsing JSON chunk', e);
                    }
                }
            }
        }
    } catch (error) {
        onError(error);
    }
};

export default {
    sendQuery,
    streamQuery,
};
