import React, { useState, useRef, useEffect } from 'react';
import { Upload, File, X, Loader2, CheckCircle, AlertCircle, Plus, Tag } from 'lucide-react';
import documentService from '../services/documentService';
import departmentService from '../services/departmentService';
import authService from '../services/authService';

const UploadForm = ({ onUploadSuccess, departments = [], onDepartmentCreated }) => {
    // State
    const [file, setFile] = useState(null);
    const [isModalOpen, setIsModalOpen] = useState(false);

    // Permission Check
    const currentUser = authService.getCurrentUser();
    const isAdmin = currentUser?.roles?.some(role => ['super_admin', 'department_admin'].includes(role));

    // Metadata State
    const [title, setTitle] = useState('');
    const [selectedDepts, setSelectedDepts] = useState(
        currentUser?.department ? [currentUser.department] : ['General']
    );
    // const [departments, setDepartments] = useState([]); // Removed local state
    const [newDeptName, setNewDeptName] = useState('');
    const [showAddDept, setShowAddDept] = useState(false);

    // Status State
    const [uploading, setUploading] = useState(false);
    const [error, setError] = useState('');
    const [success, setSuccess] = useState('');

    const fileInputRef = useRef(null);

    // Removed local useEffect and loadDepartments

    // File Validation & Handling
    const validateAndSetFile = (selectedFile) => {
        if (!selectedFile) return;

        const allowedTypes = [
            'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'text/plain', 'image/png', 'image/jpeg', 'image/jpg', 'text/csv',
            'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
        ];
        const allowedExts = ['pdf', 'docx', 'txt', 'png', 'jpg', 'jpeg', 'csv', 'xls', 'xlsx', 'ppt', 'pptx'];

        const ext = selectedFile.name.split('.').pop().toLowerCase();

        if (!allowedTypes.includes(selectedFile.type) && !allowedExts.includes(ext)) {
            setError('Supported formats: PDF, DOCX, CSV, Excel, PPT, TXT, Images');
            setFile(null);
            return;
        }

        setFile(selectedFile);
        setTitle(selectedFile.name); // Default title to filename
        setError('');
        setSuccess('');
        setIsModalOpen(true); // Open modal immediately
    };

    const handleFileChange = (e) => validateAndSetFile(e.target.files[0]);

    const handleDrop = (e) => {
        e.preventDefault();
        validateAndSetFile(e.dataTransfer.files[0]);
    };

    // Dept Management
    const toggleDepartment = (deptName) => {
        setSelectedDepts(prev => prev.includes(deptName)
            ? prev.filter(d => d !== deptName)
            : [...prev, deptName]
        );
    };

    // Local temp state to ensure immediate UI updates before parent prop propagates
    const [tempDepts, setTempDepts] = useState([]);

    // Merge departments from prop and local temp state
    const availableDepartments = [...departments];
    tempDepts.forEach(temp => {
        if (!availableDepartments.some(d => d.name === temp.name)) {
            availableDepartments.push(temp);
        }
    });

    const handleAddDepartment = async () => {
        if (!newDeptName.trim()) return;
        try {
            const newDept = await departmentService.createDepartment({ name: newDeptName });

            // 1. Notify parent to refresh global state
            if (onDepartmentCreated) {
                await onDepartmentCreated();
            }

            // 2. Add to local temp state for immediate availability in dropdown (if unselected)
            setTempDepts(prev => [...prev, newDept]);

            // 3. Auto-select the new department
            setSelectedDepts(prev => [...prev, newDept.name]);

            setNewDeptName('');
            setShowAddDept(false);
        } catch (err) {
            console.error(err);
            setError('Failed to create department');
        }
    };

    // Upload Action
    const handleUpload = async () => {
        if (!file) return;

        setUploading(true);
        setError('');

        try {
            // Updated service call signature: file, title, departments, classification
            await documentService.uploadDocument(file, title, selectedDepts);

            setSuccess('Document uploaded successfully');
            closeModal();
            if (onUploadSuccess) onUploadSuccess();
        } catch (err) {
            console.error(err);
            // Improve error display: Use specific backend message if available
            const msg = err.response?.data?.detail || 'Failed to upload document. Please try again.';
            setError(msg);
        } finally {
            setUploading(false);
        }
    };

    const closeModal = () => {
        setIsModalOpen(false);
        setFile(null);
        setTitle('');
        setSelectedDepts(currentUser?.department ? [currentUser.department] : ['General']);
        if (fileInputRef.current) fileInputRef.current.value = '';
    };

    return (
        <>
            {/* 1. Main Upload Area */}
            <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
                <h2 className="text-xl font-bold mb-4 text-gray-800">Upload Document</h2>

                {success && (
                    <div className="mb-4 flex items-center text-green-700 bg-green-50 p-3 rounded-lg border border-green-200">
                        <CheckCircle className="h-5 w-5 mr-2" />
                        {success}
                    </div>
                )}

                {error && !isModalOpen && (
                    <div className="mb-4 flex items-center text-red-700 bg-red-50 p-3 rounded-lg border border-red-200">
                        <AlertCircle className="h-5 w-5 mr-2" />
                        {error}
                    </div>
                )}

                <div
                    className="border-2 border-dashed border-gray-300 rounded-xl p-10 text-center hover:border-blue-500 hover:bg-blue-50 transition-all cursor-pointer group"
                    onDragOver={(e) => e.preventDefault()}
                    onDrop={handleDrop}
                    onClick={() => fileInputRef.current?.click()}
                >
                    <div className="flex justify-center mb-4">
                        <div className="bg-orange-100 p-4 rounded-full group-hover:scale-110 transition-transform">
                            <Upload className="h-8 w-8 text-orange-600" />
                        </div>
                    </div>
                    <p className="text-lg font-medium text-gray-700">Click or Drag file to upload</p>
                    <p className="text-sm text-gray-500 mt-2">PDF, DOCX, Images, Excel</p>
                </div>
                <input type="file" ref={fileInputRef} onChange={handleFileChange} className="hidden" />
            </div>

            {/* 2. Metadata Modal */}
            {isModalOpen && (
                <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
                    <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden animate-in fade-in zoom-in-95 duration-200">

                        {/* Header */}
                        <div className="bg-gray-50 px-6 py-4 border-b border-gray-200 flex justify-between items-center">
                            <h3 className="text-lg font-semibold text-gray-800">Finalize Upload</h3>
                            <button onClick={closeModal} className="text-gray-400 hover:text-gray-600">
                                <X className="h-5 w-5" />
                            </button>
                        </div>

                        {/* Body */}
                        <div className="p-6 space-y-6">

                            {/* File Info */}
                            <div className="flex items-center p-3 bg-blue-50 rounded-lg border border-blue-100">
                                <File className="h-8 w-8 text-blue-600 mr-3" />
                                <div className="overflow-hidden">
                                    <p className="font-medium text-blue-900 truncate">{file?.name}</p>
                                    <p className="text-xs text-blue-700">{(file?.size / 1024 / 1024).toFixed(2)} MB</p>
                                </div>
                            </div>

                            {/* SOC Title Input */}
                            <div>
                                <label className="block text-sm font-medium text-gray-700 mb-1">SOC Title / Document Name</label>
                                <input
                                    type="text"
                                    value={title}
                                    onChange={(e) => setTitle(e.target.value)}
                                    placeholder="Enter a descriptive title..."
                                    className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all"
                                    autoFocus
                                />
                            </div>

                            {/* Department Tags */}
                            <div>
                                <div className="flex justify-between items-center mb-2">
                                    <label className="block text-sm font-medium text-gray-700 flex items-center">
                                        <Tag className="h-4 w-4 mr-1" /> Departments
                                    </label>
                                </div>

                                {/* Selected Tags */}
                                <div className="flex flex-wrap gap-2 mb-3">
                                    {selectedDepts.map(deptName => (
                                        <span
                                            key={deptName}
                                            className="inline-flex items-center px-2.5 py-0.5 rounded-full text-sm font-medium bg-blue-100 text-blue-800 border border-blue-200"
                                        >
                                            {deptName}
                                            <button
                                                type="button"
                                                onClick={() => toggleDepartment(deptName)}
                                                className="ml-1.5 inline-flex items-center justify-center text-blue-400 hover:text-blue-600 focus:outline-none"
                                            >
                                                <X className="h-3 w-3" />
                                            </button>
                                        </span>
                                    ))}
                                </div>

                                {/* Dropdown & Add New */}
                                <div className="flex gap-2">
                                    <div className="relative flex-1">
                                        <select
                                            className="block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md"
                                            onChange={(e) => {
                                                if (e.target.value) {
                                                    toggleDepartment(e.target.value);
                                                    e.target.value = ""; // Reset select
                                                }
                                            }}
                                            defaultValue=""
                                        >
                                            <option value="" disabled>Select Department...</option>
                                            {availableDepartments
                                                .filter(d => !selectedDepts.includes(d.name))
                                                .map(dept => (
                                                    <option key={dept.id || dept.name} value={dept.name}>
                                                        {dept.name}
                                                    </option>
                                                ))
                                            }
                                        </select>
                                    </div>

                                    {!showAddDept && isAdmin && (
                                        <button
                                            type="button"
                                            onClick={() => setShowAddDept(true)}
                                            className="inline-flex items-center px-3 py-2 border border-blue-300 shadow-sm text-sm leading-4 font-medium rounded-md text-blue-700 bg-white hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                                        >
                                            <Plus className="h-4 w-4 mr-1" />
                                            New
                                        </button>
                                    )}
                                </div>

                                {/* Add New Input (Conditional) */}
                                {showAddDept && (
                                    <div className="mt-2 flex gap-2 animate-in fade-in slide-in-from-top-2">
                                        <input
                                            type="text"
                                            value={newDeptName}
                                            onChange={(e) => setNewDeptName(e.target.value)}
                                            placeholder="Department Name"
                                            className="flex-1 px-3 py-2 border border-gray-300 rounded-md focus:ring-blue-500 focus:border-blue-500 sm:text-sm"
                                            onKeyDown={(e) => e.key === 'Enter' && handleAddDepartment()}
                                            autoFocus
                                        />
                                        <button
                                            onClick={handleAddDepartment}
                                            className="inline-flex items-center px-3 py-2 border border-transparent text-sm leading-4 font-medium rounded-md text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                                        >
                                            Add
                                        </button>
                                        <button
                                            onClick={() => setShowAddDept(false)}
                                            className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
                                        >
                                            Cancel
                                        </button>
                                    </div>
                                )}
                            </div>

                            {error && (
                                <div className="text-red-600 text-sm bg-red-50 p-3 rounded-lg flex items-center">
                                    <AlertCircle className="h-4 w-4 mr-2" />
                                    {error}
                                </div>
                            )}

                        </div>

                        {/* Footer */}
                        <div className="bg-gray-50 px-6 py-4 border-t border-gray-200 flex justify-end gap-3">
                            <button
                                onClick={closeModal}
                                disabled={uploading}
                                className="px-4 py-2 text-gray-700 font-medium hover:bg-gray-100 rounded-lg transition-colors"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={handleUpload}
                                disabled={uploading || !title}
                                className="flex items-center px-6 py-2 bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-medium rounded-lg hover:from-blue-700 hover:to-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed shadow-md transition-all hover:shadow-lg"
                            >
                                {uploading ? (
                                    <>
                                        <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                                        Uploading...
                                    </>
                                ) : (
                                    <>
                                        <Upload className="h-4 w-4 mr-2" />
                                        Confirm Upload
                                    </>
                                )}
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </>
    );
};

export default UploadForm;
