import api from './api';

const departmentService = {
    getDepartments: async () => {
        const response = await api.get('/departments/');
        return response.data;
    },

    createDepartment: async (departmentData) => {
        const response = await api.post('/departments/', departmentData);
        return response.data;
    }
};

export default departmentService;
