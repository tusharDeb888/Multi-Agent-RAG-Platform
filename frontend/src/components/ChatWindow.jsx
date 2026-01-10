import React, { useRef, useEffect, useState } from 'react';
import { Send, User, Bot, Loader2, Copy, Check, Edit2, X, Save, RotateCcw } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import 'katex/dist/katex.min.css'; // Import KaTeX CSS
import CitationViewer from './CitationViewer';

const ChatWindow = ({ messages, onSendMessage, onEditMessage, onRegenerate, loading }) => {
    const messagesEndRef = useRef(null);
    const [input, setInput] = React.useState('');
    const [editingIndex, setEditingIndex] = useState(-1);
    const [editValue, setEditValue] = useState('');
    const [copiedIndex, setCopiedIndex] = useState(-1); // Track which message was copied

    const handleCopyMsg = (text, index) => {
        navigator.clipboard.writeText(text);
        setCopiedIndex(index);
        setTimeout(() => setCopiedIndex(-1), 2000);
    };

    const startEditing = (index, content) => {
        setEditingIndex(index);
        setEditValue(content);
    };

    const cancelEdit = () => {
        setEditingIndex(-1);
        setEditValue('');
    };

    const saveEdit = (index) => {
        if (editValue.trim()) {
            onEditMessage(index, editValue);
            cancelEdit();
        }
    };

    const scrollToBottom = () => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    };

    useEffect(() => {
        scrollToBottom();
    }, [messages, loading]);

    const handleSubmit = (e) => {
        e.preventDefault();
        if (input.trim() && !loading) {
            onSendMessage(input);
            setInput('');
        }
    };

    // Helper to strip citation tags from display
    const cleanContent = (text) => {
        if (!text) return "";
        let cleaned = text.replace(/\[\[\s*\d+\s*\]\]/g, "");
        // Remove "Citation" header if it exists (Markdown or Bold)
        cleaned = cleaned.replace(/(\n|^)(#{1,6}|\*\*)\s*Citation(s)?\s*(\*\*|:)?\s*(\n|$)/gmi, "");
        return cleaned.trim();
    };

    const components = {
        // Custom link renderer to open in new tab
        a: ({ node, ...props }) => (
            <a {...props} target="_blank" rel="noopener noreferrer" className="text-orange-600 hover:text-orange-800 underline transition-colors" />
        ),
        // Premium Table Styling
        table: ({ node, ...props }) => (
            <div className="overflow-x-auto my-6 rounded-lg border border-gray-200 shadow-sm ring-1 ring-black/5">
                <table {...props} className="min-w-full divide-y divide-gray-200 text-sm" />
            </div>
        ),
        thead: ({ node, ...props }) => (
            <thead {...props} className="bg-gray-50/75 backdrop-blur supports-[backdrop-filter]:bg-gray-50/75" />
        ),
        th: ({ node, ...props }) => (
            <th {...props} className="px-6 py-3 text-left text-xs font-semibold text-gray-900 uppercase tracking-wider border-b border-gray-200" />
        ),
        tbody: ({ node, ...props }) => (
            <tbody {...props} className="divide-y divide-gray-200 bg-white" />
        ),
        tr: ({ node, ...props }) => (
            <tr {...props} className="hover:bg-gray-50/50 transition-colors even:bg-gray-50/30" />
        ),
        td: ({ node, ...props }) => (
            <td {...props} className="px-6 py-4 text-gray-700 whitespace-normal leading-relaxed" />
        ),
        // Improved Blockquote
        blockquote: ({ node, ...props }) => (
            <blockquote {...props} className="border-l-4 border-orange-400 pl-4 py-2 my-4 bg-orange-50/30 italic text-gray-700 rounded-r-md" />
        ),
        // Code implementation with Copy Button & Syntax Highlighting
        code({ node, inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            const [copied, setCopied] = React.useState(false);
            const codeText = String(children).replace(/\n$/, '');

            const handleCopy = () => {
                navigator.clipboard.writeText(codeText);
                setCopied(true);
                setTimeout(() => setCopied(false), 2000);
            };

            return !inline && match ? (
                <div className="relative group my-6 rounded-lg overflow-hidden shadow-md border border-gray-200/60 ring-1 ring-gray-900/5">
                    {/* Header with Language and Copy Button */}
                    <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-200/60">
                        <span className="text-xs font-semibold text-gray-500 uppercase tracking-wider font-mono">
                            {match[1]}
                        </span>
                        <button
                            onClick={handleCopy}
                            className="flex items-center gap-1.5 px-2 py-1 text-xs font-medium text-gray-500 hover:text-gray-700 hover:bg-gray-200/50 rounded-md transition-all focus:outline-none"
                            title="Copy code"
                        >
                            {copied ? (
                                <>
                                    <Check className="h-3.5 w-3.5 text-green-600" />
                                    <span className="text-green-600">Copied!</span>
                                </>
                            ) : (
                                <>
                                    <Copy className="h-3.5 w-3.5" />
                                    <span>Copy</span>
                                </>
                            )}
                        </button>
                    </div>

                    <SyntaxHighlighter
                        style={oneDark}
                        language={match[1]}
                        PreTag="div"
                        {...props}
                        customStyle={{ margin: 0, padding: '1.5rem', borderRadius: 0, fontSize: '0.9em' }}
                    >
                        {codeText}
                    </SyntaxHighlighter>
                </div>
            ) : (
                <code className={`${className} bg-gray-100 text-pink-600 rounded px-1.5 py-0.5 text-sm font-mono border border-gray-200`} {...props}>
                    {children}
                </code>
            );
        },
        // Headings
        h1: ({ node, ...props }) => <h1 {...props} className="text-2xl font-bold text-gray-900 border-b pb-2 mb-4 mt-6 scroll-mt-20" />,
        h2: ({ node, ...props }) => <h2 {...props} className="text-xl font-semibold text-gray-800 mb-3 mt-5 scroll-mt-20" />,
        h3: ({ node, ...props }) => <h3 {...props} className="text-lg font-medium text-gray-800 mb-2 mt-4 scroll-mt-20" />,
        // Lists
        ul: ({ node, ...props }) => <ul {...props} className="list-disc list-outside ml-5 space-y-1.5 my-3 text-gray-700 marker:text-gray-400" />,
        ol: ({ node, ...props }) => <ol {...props} className="list-decimal list-outside ml-5 space-y-1.5 my-3 text-gray-700 marker:text-gray-500 font-medium" />,
        li: ({ node, ...props }) => <li {...props} className="pl-1" />,
    };

    return (
        <div className="flex flex-col h-full bg-gray-50/50 rounded-xl shadow-lg border border-gray-200/60 backdrop-blur-sm overflow-hidden">
            {/* Messages Area */}
            <div className="flex-1 overflow-y-auto p-4 space-y-8 scroll-smooth">
                {messages.length === 0 ? (
                    <div className="flex flex-col items-center justify-center h-full text-gray-400 space-y-6 animate-fade-in-up">
                        <div className="p-4 bg-white rounded-full shadow-sm border border-gray-100">
                            <Bot className="h-12 w-12 text-orange-600/80" />
                        </div>
                        <div className="text-center space-y-2">
                            <p className="text-xl font-semibold text-gray-700">IOCL AI Chat System</p>
                            <p className="text-sm text-gray-500 max-w-xs mx-auto">
                                Ask me about your technical specifications, financial reports, or internal procedures.
                            </p>
                        </div>
                    </div>
                ) : (
                    messages.map((msg, index) => (
                        <div
                            key={index}
                            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'} animate-fade-in`}
                        >
                            <div
                                className={`flex max-w-[85%] sm:max-w-[75%] gap-4 ${msg.role === 'user' ? 'flex-row-reverse' : 'flex-row'
                                    }`}
                            >
                                {/* Avatar */}
                                <div
                                    className={`flex-shrink-0 h-10 w-10 rounded-full flex items-center justify-center shadow-sm ${msg.role === 'user'
                                        ? 'bg-white-600 text-orange-600 ring-2 ring-gray-100'
                                        : 'bg-white text-orange-600 ring-2 ring-gray-100 border border-gray-200'
                                        }`}
                                >
                                    {msg.role === 'user' ? (
                                        <User className="h-5 w-5" />
                                    ) : (
                                        <Bot className="h-6 w-6" />
                                    )}
                                </div>

                                {/* Bubble */}
                                <div className="flex flex-col space-y-1 min-w-0 group">
                                    <div
                                        className={`p-5 rounded-2xl shadow-sm text-base leading-relaxed ${msg.role === 'user'
                                            ? 'bg-orange-600 text-white rounded-tr-none'
                                            : 'bg-white text-gray-800 border border-gray-100 rounded-tl-none ring-1 ring-gray-900/5'
                                            }`}
                                    >
                                        {editingIndex === index ? (
                                            <div className="w-full">
                                                <textarea
                                                    value={editValue}
                                                    onChange={(e) => setEditValue(e.target.value)}
                                                    className="w-full p-2 text-gray-800 bg-white rounded border border-orange-300 focus:outline-none focus:ring-2 focus:ring-orange-500 min-h-[80px]"
                                                />
                                                <div className="flex justify-end gap-2 mt-2">
                                                    <button
                                                        onClick={cancelEdit}
                                                        className="p-1 text-orange-100 hover:text-white"
                                                        title="Cancel"
                                                    >
                                                        <X className="h-5 w-5" />
                                                    </button>
                                                    <button
                                                        onClick={() => saveEdit(index)}
                                                        className="p-1 text-white hover:text-green-200"
                                                        title="Save & Submit"
                                                    >
                                                        <Save className="h-5 w-5" />
                                                    </button>
                                                </div>
                                            </div>
                                        ) : (
                                            <>
                                                {msg.status && msg.isStreaming && (
                                                    <div className="flex items-center text-xs text-orange-600 mb-3 font-mono bg-orange-50 px-2 py-1 rounded w-fit">
                                                        <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
                                                        <span className="uppercase tracking-wider">{msg.status}</span>
                                                    </div>
                                                )}

                                                <div className={`prose prose-sm md:prose-base max-w-none ${msg.role === 'user'
                                                    ? 'prose-invert text-white prose-p:leading-relaxed prose-pre:bg-orange-800 prose-pre:border-orange-700'
                                                    : 'text-gray-800 prose-headings:text-gray-900 prose-a:text-orange-600 prose-strong:text-gray-900'
                                                    }`}>
                                                    <ReactMarkdown
                                                        remarkPlugins={[remarkGfm, remarkMath]}
                                                        rehypePlugins={[rehypeKatex]}
                                                        components={components}
                                                    >
                                                        {cleanContent(msg.content)}
                                                    </ReactMarkdown>
                                                </div>
                                            </>
                                        )}

                                        {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && (
                                            <div className="mt-4 pt-4 border-t border-gray-100">
                                                <CitationViewer citations={msg.citations} />
                                            </div>
                                        )}

                                    </div>

                                    {/* Action Bar (Outside Bubble) */}
                                    <div className={`flex items-center justify-end gap-1 mt-1 px-1 ${editingIndex !== index ? 'opacity-0 group-hover:opacity-100 transition-opacity duration-200' : 'opacity-100'}`}>

                                        {/* Copy Button */}
                                        <button
                                            onClick={() => handleCopyMsg(msg.content, index)}
                                            className="p-1.5 text-gray-500 hover:text-black rounded-lg hover:bg-gray-100 transition-all font-medium"
                                            title="Copy"
                                        >
                                            {copiedIndex === index ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                                        </button>

                                        {/* Regenerate Button (Both User & Assistant) */}
                                        <button
                                            onClick={() => onRegenerate(index)}
                                            className="p-1.5 text-gray-500 hover:text-black rounded-lg hover:bg-gray-100 transition-all font-medium"
                                            title="Regenerate"
                                        >
                                            <RotateCcw className="h-4 w-4" />
                                        </button>

                                        {/* Edit Button (User Only) */}
                                        {msg.role === 'user' && (
                                            <button
                                                onClick={() => startEditing(index, msg.content)}
                                                className="p-1.5 text-gray-500 hover:text-black rounded-lg hover:bg-gray-100 transition-all font-medium"
                                                title="Edit"
                                            >
                                                <Edit2 className="h-4 w-4" />
                                            </button>
                                        )}
                                    </div>
                                </div>

                                {/* Timestamp/Status (Optional, can add later) */}
                                {/* <span className="text-xs text-gray-400 px-1">
                                        {msg.role === 'user' ? 'You' : 'AI Assistant'}
                                    </span> */}
                            </div>
                        </div>
                    ))
                )}

                <div ref={messagesEndRef} className="h-4" />
            </div>

            {/* Input Area */}
            <div className="p-4 bg-white/80 backdrop-blur-md border-t border-gray-200">
                <form onSubmit={handleSubmit} className="flex gap-3 max-w-4xl mx-auto relative">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        placeholder="Ask a follow-up question..."
                        className="flex-1 px-5 py-4 rounded-xl border border-gray-200 focus:outline-none focus:ring-2 focus:ring-blue-500/20 focus:border-blue-500 shadow-sm text-gray-700 placeholder-gray-400 bg-white transition-all"
                        disabled={loading}
                    />
                    <button
                        type="submit"
                        disabled={!input.trim() || loading}
                        className="px-6 py-4 bg-orange-600 text-white rounded-xl hover:bg-orange-700 focus:outline-none focus:ring-4 focus:ring-orange-500/30 disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-orange-500/20 transition-all hover:scale-[1.02] active:scale-[0.98] flex items-center font-medium"
                    >
                        <span className="hidden sm:inline mr-2">Send</span>
                        <Send className="h-5 w-5" />
                    </button>

                    {/* Add Attachment Button could go here */}
                </form>
                {/* Footer note */}
                <div className="text-center mt-2">
                    <p className="text-[10px] text-gray-400 uppercase tracking-widest font-medium">Powered by IOCL AI RAG Architecture</p>
                </div>
            </div>
        </div >
    );
};

export default ChatWindow;
