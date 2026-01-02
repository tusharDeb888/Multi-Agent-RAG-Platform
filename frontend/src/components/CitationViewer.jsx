import React from 'react';
import { FileText, ExternalLink } from 'lucide-react';
import storageService from '../services/storageService';

const CitationViewer = ({ citations }) => {
    if (!citations || citations.length === 0) return null;

    const token = storageService.getItem('token', false);

    return (
        <div className="mt-4 pt-4 border-t border-gray-100">
            <h4 className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
                Sources
            </h4>
            <div className="flex flex-wrap gap-2">
                {citations.map((citation, index) => (
                    <a
                        key={`${citation.document_id}-${index}`}
                        href={`http://localhost:8000/api/v1/documents/${citation.document_id}/content/${encodeURIComponent(citation.document_name)}?token=${token}#page=${citation.page_number}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-center bg-blue-50 text-blue-700 px-3 py-1.5 rounded-md text-sm border border-blue-100 hover:bg-blue-100 transition-colors cursor-pointer decoration-0"
                        title={`Click to open ${citation.document_name} at page ${citation.page_number}`}
                    >
                        <FileText className="h-3.5 w-3.5 mr-1.5" />
                        <span className="font-medium truncate max-w-[150px]">
                            {citation.document_name}
                        </span>
                        <span className="ml-1.5 text-blue-400">|</span>
                        <span className="ml-1.5 text-xs">Page {citation.page_number}</span>
                    </a>
                ))}
            </div>
        </div>
    );
};

export default CitationViewer;
