import React, { useState } from 'react';
import { FileText, Clock, CheckCircle, AlertTriangle, Trash2, Edit2, Save, X } from 'lucide-react';
import authService from '../services/authService';
import documentService from '../services/documentService';

const DocumentList = ({ documents, departments = [], onDelete, onUpdate }) => {
    const [editingId, setEditingId] = useState(null);
    const [editDepts, setEditDepts] = useState([]);

    const startEdit = (doc) => {
        setEditingId(doc.id);
        setEditDepts(doc.departments || (doc.department ? [doc.department] : []));
    };

    const cancelEdit = () => {
        setEditingId(null);
        setEditDepts([]);
    };

    const saveEdit = async (id) => {
        try {
            await documentService.updateDocument(id, { departments: editDepts });
            setEditingId(null);
            if (onUpdate) onUpdate();
        } catch (err) {
            console.error("Failed to update doc", err);
            alert("Failed to update tags");
        }
    };

    const toggleEditDept = (deptName) => {
        setEditDepts(prev => prev.includes(deptName)
            ? prev.filter(d => d !== deptName)
            : [...prev, deptName]
        );
    };

    const user = authService.getCurrentUser();
    const isAdmin = user?.roles?.includes('super_admin') || user?.roles?.includes('department_admin');
    const getStatusBadge = (status) => {
        switch (status) {
            case 'completed':
            case 'searchable':
                return (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                        <CheckCircle className="w-3 h-3 mr-1" /> Ready
                    </span>
                );
            case 'processing':
                return (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-orange-100 text-orange-800">
                        <Clock className="w-3 h-3 mr-1 animate-pulse" /> Processing
                    </span>
                );
            case 'partial':
                return (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-yellow-100 text-yellow-800">
                        <Clock className="w-3 h-3 mr-1 animate-pulse" /> Indexing...
                    </span>
                );
            case 'failed':
                return (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-red-100 text-red-800">
                        <AlertTriangle className="w-3 h-3 mr-1" /> Failed
                    </span>
                );
            default:
                return (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                        <Clock className="w-3 h-3 mr-1" /> Pending
                    </span>
                );
        }
    };

    return (
        <div className="bg-white rounded-lg shadow-sm border border-gray-200 overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200">
                <h3 className="text-lg font-semibold text-gray-800">Recent Documents</h3>
            </div>

            <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-gray-200">
                    <thead className="bg-gray-50">
                        <tr>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Document Name
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Status
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Department
                            </th>
                            <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                                Uploaded At
                            </th>
                            {(isAdmin || onDelete) && (
                                <th className="px-6 py-3 text-right text-xs font-medium text-gray-500 uppercase tracking-wider">
                                    Actions
                                </th>
                            )}
                        </tr>
                    </thead>
                    <tbody className="bg-white divide-y divide-gray-200">
                        {documents.length === 0 ? (
                            <tr>
                                <td colSpan={isAdmin ? "5" : "4"} className="px-6 py-8 text-center text-gray-500">
                                    No documents found. Upload one to get started.
                                </td>
                            </tr>
                        ) : (
                            documents.map((doc) => (
                                <tr key={doc.id} className="hover:bg-gray-50 transition-colors">
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        <div className="flex items-center">
                                            <FileText className="h-5 w-5 text-gray-400 mr-3" />
                                            <div>
                                                <div className="text-sm font-medium text-gray-900">{doc.title || doc.filename}</div>
                                                {doc.title && doc.title !== doc.filename && (
                                                    <div className="text-xs text-gray-500">{doc.filename}</div>
                                                )}
                                            </div>
                                        </div>
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap">
                                        {getStatusBadge(doc.status)}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                        {editingId === doc.id ? (
                                            <div className="flex flex-wrap gap-1 max-w-xs">
                                                {departments.map(dept => (
                                                    <button
                                                        key={dept.id}
                                                        onClick={() => toggleEditDept(dept.name)}
                                                        className={`px-2 py-0.5 text-xs rounded border ${editDepts.includes(dept.name)
                                                            ? 'bg-blue-100 text-blue-800 border-blue-300'
                                                            : 'bg-gray-50 text-gray-400 border-gray-200'
                                                            }`}
                                                    >
                                                        {dept.name}
                                                    </button>
                                                ))}
                                            </div>
                                        ) : (
                                            <div className="flex flex-wrap gap-1">
                                                {doc.departments && doc.departments.length > 0 ? (
                                                    doc.departments.map((d, i) => (
                                                        <span key={i} className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-gray-100 text-gray-800">
                                                            {d}
                                                        </span>
                                                    ))
                                                ) : (
                                                    <span className="text-gray-400 italic">None</span>
                                                )}
                                            </div>
                                        )}
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                                        {new Date(doc.uploaded_at).toLocaleDateString()}
                                    </td>
                                    {(isAdmin || onDelete) && (
                                        <td className="px-6 py-4 whitespace-nowrap text-right text-sm font-medium">
                                            {editingId === doc.id ? (
                                                <div className="flex items-center justify-end space-x-2">
                                                    <button onClick={() => saveEdit(doc.id)} className="text-green-600 hover:text-green-900">
                                                        <Save className="h-5 w-5" />
                                                    </button>
                                                    <button onClick={cancelEdit} className="text-gray-600 hover:text-gray-900">
                                                        <X className="h-5 w-5" />
                                                    </button>
                                                </div>
                                            ) : (
                                                <div className="flex items-center justify-end space-x-2">
                                                    {(isAdmin) && (
                                                        <button
                                                            onClick={() => startEdit(doc)}
                                                            className="text-blue-600 hover:text-blue-900 focus:outline-none"
                                                            title="Edit Tags"
                                                        >
                                                            <Edit2 className="h-5 w-5" />
                                                        </button>
                                                    )}
                                                    {(isAdmin || onDelete) && (
                                                        <button
                                                            onClick={() => onDelete && onDelete(doc.id)}
                                                            className="text-red-600 hover:text-red-900 focus:outline-none"
                                                            title="Delete Document"
                                                        >
                                                            <Trash2 className="h-5 w-5" />
                                                        </button>
                                                    )}
                                                </div>
                                            )}
                                        </td>
                                    )}
                                </tr>
                            ))
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
};

export default DocumentList;
