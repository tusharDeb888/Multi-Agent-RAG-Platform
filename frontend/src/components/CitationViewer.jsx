import React from 'react';
import { FileText, ExternalLink } from 'lucide-react';
import storageService from '../services/storageService';

const CitationViewer = ({ citations }) => {
    if (!citations || citations.length === 0) return null;

    const token = storageService.getItem('token', false);

    const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';

    // Ensure API_URL doesn't end with slash if we append path starting with slash
    // But backend routes usually start with slash. 
    // Let's assume VITE_API_URL is the root API endpoint (e.g. /api/v1)
    // If VITE_API_URL is just domain, we need to add /api/v1. 
    // Best practice: VITE_API_URL provided by build/env includes /api/v1

    const getDocumentUrl = (docId, filename, page) => {
        // Remove trailing slash if present
        const baseUrl = API_URL.replace(/\/$/, '');
        return `${baseUrl}/documents/${docId}/content/${encodeURIComponent(filename)}?token=${token}#page=${page}`;
    };

    return (
        <div className="mt-4 pt-4 border-t border-gray-100">
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Sources
            </h4>
            <div className="flex flex-wrap gap-2">
                {citations.map((citation, index) => (
                    <div
                        key={`${citation.document_id}-${index}`}
                        className="inline-flex items-center bg-blue-50 text-blue-700 rounded-md border border-blue-100 overflow-hidden mr-2 mb-2"
                    >
                        <a
                            href={getDocumentUrl(citation.document_id, citation.document_name, citation.page_number)}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="flex items-center px-3 py-1.5 hover:bg-orange-100 transition-colors cursor-pointer decoration-0"
                            title={`Click to open ${citation.document_name} at page ${citation.page_number}\nSnippet: "${citation.snippet || 'No snippet available'}"`}
                        >
                            <FileText className="h-3.5 w-3.5 mr-1.5" />
                            <span className="font-medium truncate max-w-[150px]">
                                [{citation.index || index + 1}] {citation.document_name}
                            </span>
                            <span className="ml-1.5 text-blue-400">|</span>
                            <span className="ml-1.5 text-xs">Page {citation.page_number}</span>
                        </a>

                        {citation.source_url && (
                            <a
                                href={citation.source_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="flex items-center justify-center px-2 py-1.5 hover:bg-blue-100 border-l border-blue-200 transition-colors cursor-pointer"
                                title={`Open Source URL: ${citation.source_url}`}
                            >
                                <ExternalLink className="h-3.5 w-3.5" />
                            </a>
                        )}
                    </div>
                ))}
            </div>
        </div>
    );
};

export default CitationViewer;
