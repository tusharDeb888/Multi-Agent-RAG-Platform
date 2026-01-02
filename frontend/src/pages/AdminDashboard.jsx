import React, { useEffect, useState } from 'react';
import UploadForm from '../components/UploadForm';
import DocumentList from '../components/DocumentList';
import documentService from '../services/documentService';
import authService from '../services/authService';
import departmentService from '../services/departmentService';
import { Plus } from 'lucide-react';



const AdminDashboard = () => {
    const [documents, setDocuments] = useState([]);
    const [departments, setDepartments] = useState([]);
    const [loading, setLoading] = useState(true);

    const fetchDepartments = async () => {
        try {
            const depts = await departmentService.getDepartments();
            setDepartments(depts);
        } catch (error) {
            console.error('Failed to fetch departments:', error);
        }
    };

    const fetchDocuments = async () => {
        try {
            const docs = await documentService.getDocuments();
            setDocuments(docs);
        } catch (error) {
            console.error('Failed to fetch documents:', error);
        } finally {
            setLoading(false);
        }
    };

    useEffect(() => {
        // Only fetch and poll if user is authenticated
        const token = authService.getToken();
        if (!token) {
            setLoading(false);
            return;
        }

        fetchDocuments();
        fetchDepartments();

        // Poll for updates every 5 seconds (only if authenticated)
        const interval = setInterval(() => {
            // Re-check auth before each poll
            if (authService.getToken()) {
                fetchDocuments();
            } else {
                clearInterval(interval);
            }
        }, 5000);

        return () => clearInterval(interval);
    }, []);

    const user = authService.getCurrentUser();
    const isAdmin = user?.roles?.includes('super_admin') || user?.roles?.includes('department_admin');

    const handleDelete = async (id) => {
        if (window.confirm('Are you sure you want to delete this document? This cannot be undone.')) {
            try {
                await documentService.deleteDocument(id);
                // Refresh list immediately
                fetchDocuments();
            } catch (error) {
                console.error('Failed to delete document:', error);
                alert('Failed to delete document');
            }
        }
    };

    return (
        <div className="space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-gray-900">Document Dashboard</h1>
                <p className="text-gray-600">Manage documents and system status</p>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
                {/* Upload Section - Admins Only */}
                {isAdmin && (
                    <div className="lg:col-span-1">
                        <UploadForm
                            departments={departments}
                            onDepartmentCreated={fetchDepartments}
                            onUploadSuccess={() => { fetchDocuments(); fetchDepartments(); }}
                        />

                    </div>
                )}

                {/* Document List Section */}
                <div className={isAdmin ? "lg:col-span-2" : "lg:col-span-3"}>
                    <DocumentList
                        documents={documents}
                        departments={departments}
                        onDelete={isAdmin ? handleDelete : null}
                        onUpdate={fetchDocuments}
                    />
                </div>
            </div>
        </div>
    );
};

export default AdminDashboard;
