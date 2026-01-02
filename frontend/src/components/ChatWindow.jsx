import React, { useRef, useEffect } from 'react';
import { Send, User, Bot, Loader2 } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import remarkMath from 'remark-math';
import rehypeKatex from 'rehype-katex';
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter';
import { oneDark } from 'react-syntax-highlighter/dist/esm/styles/prism';
import 'katex/dist/katex.min.css'; // Import KaTeX CSS
import CitationViewer from './CitationViewer';

const ChatWindow = ({ messages, onSendMessage, loading }) => {
    const messagesEndRef = useRef(null);
    const [input, setInput] = React.useState('');

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
            <a {...props} target="_blank" rel="noopener noreferrer" className="text-blue-600 hover:text-blue-800 underline transition-colors" />
        ),
        // Style tables broadly with better borders and shadow
        table: ({ node, ...props }) => (
            <div className="overflow-x-auto my-4 rounded-lg border border-gray-200 shadow-sm">
                <table {...props} className="min-w-full divide-y divide-gray-200" />
            </div>
        ),
        th: ({ node, ...props }) => (
            <th {...props} className="px-4 py-3 bg-gray-50 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider" />
        ),
        td: ({ node, ...props }) => (
            <td {...props} className="px-4 py-3 border-t border-gray-200 text-sm text-gray-700 bg-white" />
        ),
        // Improved Blockquote
        blockquote: ({ node, ...props }) => (
            <blockquote {...props} className="border-l-4 border-blue-400 pl-4 py-2 my-4 bg-blue-50/50 italic text-gray-700" />
        ),
        // Code implementation with Syntax Highlighting
        code({ node, inline, className, children, ...props }) {
            const match = /language-(\w+)/.exec(className || '');
            return !inline && match ? (
                <div className="relative group my-4 rounded-md overflow-hidden shadow-lg border border-gray-100">
                    <div className="absolute top-0 right-0 px-2 py-1 text-xs text-gray-400 bg-gray-800/80 rounded-bl backdrop-blur-sm opacity-0 group-hover:opacity-100 transition-opacity">
                        {match[1]}
                    </div>
                    <SyntaxHighlighter
                        style={oneDark}
                        language={match[1]}
                        PreTag="div"
                        {...props}
                        customStyle={{ margin: 0, padding: '1.5rem', borderRadius: 0 }}
                    >
                        {String(children).replace(/\n$/, '')}
                    </SyntaxHighlighter>
                </div>
            ) : (
                <code className={`${className} bg-gray-100 text-pink-600 rounded px-1.5 py-0.5 text-sm font-mono border border-gray-200`} {...props}>
                    {children}
                </code>
            );
        },
        // Headings
        h1: ({ node, ...props }) => <h1 {...props} className="text-2xl font-bold text-gray-900 border-b pb-2 mb-4 mt-6" />,
        h2: ({ node, ...props }) => <h2 {...props} className="text-xl font-semibold text-gray-800 mb-3 mt-5" />,
        h3: ({ node, ...props }) => <h3 {...props} className="text-lg font-medium text-gray-800 mb-2 mt-4" />,
        // Lists
        ul: ({ node, ...props }) => <ul {...props} className="list-disc list-outside ml-5 space-y-1 my-3 text-gray-700" />,
        ol: ({ node, ...props }) => <ol {...props} className="list-decimal list-outside ml-5 space-y-1 my-3 text-gray-700" />,
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
                                <div className="flex flex-col space-y-1 min-w-0">
                                    <div
                                        className={`p-5 rounded-2xl shadow-sm text-base leading-relaxed ${msg.role === 'user'
                                            ? 'bg-orange-600 text-white rounded-tr-none'
                                            : 'bg-white text-gray-800 border border-gray-100 rounded-tl-none ring-1 ring-gray-900/5'
                                            }`}
                                    >
                                        {msg.status && msg.isStreaming && (
                                            <div className="flex items-center text-xs text-blue-500 mb-3 font-mono bg-blue-50 px-2 py-1 rounded w-fit">
                                                <Loader2 className="h-3 w-3 animate-spin mr-1.5" />
                                                <span className="uppercase tracking-wider">{msg.status}</span>
                                            </div>
                                        )}

                                        <div className={`prose prose-sm md:prose-base max-w-none ${msg.role === 'user'
                                            ? 'prose-invert text-white prose-p:leading-relaxed prose-pre:bg-blue-800 prose-pre:border-blue-700'
                                            : 'text-gray-800 prose-headings:text-gray-900 prose-a:text-blue-600 prose-strong:text-gray-900'
                                            }`}>
                                            <ReactMarkdown
                                                remarkPlugins={[remarkGfm, remarkMath]}
                                                rehypePlugins={[rehypeKatex]}
                                                components={components}
                                            >
                                                {cleanContent(msg.content)}
                                            </ReactMarkdown>
                                        </div>

                                        {msg.role === 'assistant' && msg.citations && msg.citations.length > 0 && (
                                            <div className="mt-4 pt-4 border-t border-gray-100">
                                                <CitationViewer citations={msg.citations} />
                                            </div>
                                        )}
                                    </div>

                                    {/* Timestamp/Status (Optional, can add later) */}
                                    {/* <span className="text-xs text-gray-400 px-1">
                                        {msg.role === 'user' ? 'You' : 'AI Assistant'}
                                    </span> */}
                                </div>
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
