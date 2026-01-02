import api from './api';

const uploadDocument = async (file, title, departments = ['General'], classification = 'internal') => {
    const formData = new FormData();
    formData.append('file', file);
    if (title) formData.append('title', title);

    // Ensure departments is a JSON string
    const deptsJson = typeof departments === 'string' ? departments : JSON.stringify(departments);
    formData.append('departments', deptsJson);

    formData.append('classification', classification);

    const response = await api.post('/documents/upload', formData, {
        headers: {
            'Content-Type': 'multipart/form-data',
        },
    });
    return response.data;
};

const getDocuments = async () => {
    const response = await api.get('/documents/');
    return response.data;
};

const deleteDocument = async (id) => {
    await api.delete(`/documents/${id}`);
};

const updateDocument = async (id, data) => {
    const response = await api.patch(`/documents/${id}`, data);
    return response.data;
};

export default {
    uploadDocument,
    getDocuments,
    deleteDocument,
    updateDocument,
};
