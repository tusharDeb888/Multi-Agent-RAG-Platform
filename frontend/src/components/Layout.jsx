import React from 'react';
import { Link, useNavigate, useLocation } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, LogOut, Menu, X, History } from 'lucide-react';
import authService from '../services/authService';
import imgLogo from "../assets/IndianOilLogo1024x768.jpeg";
import { Plus } from 'lucide-react';

import storageService from '../services/storageService';

const Layout = ({ children }) => {
    const navigate = useNavigate();
    const location = useLocation();
    const [isSidebarOpen, setIsSidebarOpen] = React.useState(false);

    const user = authService.getCurrentUser();
    const isAdmin = user?.roles?.includes('super_admin') || user?.roles?.includes('department_admin');

    const handleLogout = () => {
        authService.logout();
        navigate('/login');
    };

    const handleNewChat = () => {
        // Clear chat session history
        storageService.removeItem('chat_session_messages');

        // Force refresh/reset chat if on chat page, or navigate there
        if (location.pathname === '/chat') {
            window.location.reload();
        } else {
            navigate('/chat');
        }
    };

    const menuItems = [
        { path: '/chat', label: 'Chat', icon: MessageSquare },
        { path: '/history', label: 'Chat History', icon: History },
        { path: '/admin', label: 'Admin Dashboard', icon: LayoutDashboard, adminOnly: true },
    ];

    return (
        <div className="flex h-screen bg-white">
            {/* Sidebar */}
            <aside
                className={`fixed inset-y-0 left-0 z-50 w-72 bg-white border-r border-gray-100 transform transition-transform duration-300 ease-in-out ${isSidebarOpen ? 'translate-x-0' : '-translate-x-full'
                    } md:relative md:translate-x-0 flex flex-col`}
            >
                {/* Branding Area */}
                <div className="flex flex-col items-center justify-center p-6 border-b border-gray-100">
                    <div className="relative h-24 w-24 mb-4 rounded-full border-4 border-blue-600/10 p-1 flex items-center justify-center overflow-hidden bg-white shadow-sm">
                        <img
                            src={imgLogo}
                            alt="IndianOil Logo"
                            className="h-full w-full object-cover rounded-full"
                        />
                    </div>
                    <h1 className="text-xl font-bold text-blue-900 tracking-tight">IndianOil</h1>

                    <button onClick={() => setIsSidebarOpen(false)} className="md:hidden absolute top-4 right-4">
                        <X className="h-6 w-6 text-gray-400" />
                    </button>

                    {/* New Chat Button */}
                    <button
                        onClick={handleNewChat}
                        className="mt-6 w-full flex items-center justify-center space-x-2 bg-orange-500 hover:bg-orange-600 text-white px-4 py-2.5 rounded-lg transition-colors font-medium shadow-sm shadow-orange-500/20"
                    >
                        <Plus className="h-5 w-5" />
                        <span>New Chat</span>
                    </button>
                </div>

                <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
                    {menuItems.map((item) => {
                        if (item.adminOnly && !isAdmin) return null;

                        const Icon = item.icon;
                        const isActive = location.pathname === item.path;
                        return (
                            <Link
                                key={item.path}
                                to={item.path}
                                className={`flex items-center space-x-3 px-4 py-3 rounded-lg transition-all group ${isActive
                                    ? 'bg-orange-50 text-orange-600 font-medium'
                                    : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
                                    }`}
                            >
                                <Icon className={`h-5 w-5 transition-colors ${isActive ? 'text-orange-500' : 'text-gray-400 group-hover:text-gray-600'}`} />
                                <span>{item.label}</span>
                            </Link>
                        );
                    })}
                </nav>

                <div className="p-4 border-t border-gray-100">
                    <button
                        onClick={handleLogout}
                        className="flex items-center space-x-3 px-4 py-3 w-full text-gray-500 hover:bg-red-50 hover:text-red-600 rounded-lg transition-colors"
                    >
                        <LogOut className="h-5 w-5" />
                        <span className="font-medium">Logout</span>
                    </button>
                </div>
            </aside>

            {/* Main Content */}
            <div className="flex-1 flex flex-col overflow-hidden bg-white">
                {/* Mobile Header */}
                <header className="md:hidden bg-white border-b border-gray-100 p-4 flex items-center justify-between">
                    <div className="flex items-center">
                        <button onClick={() => setIsSidebarOpen(true)} className="mr-3">
                            <Menu className="h-6 w-6 text-gray-600" />
                        </button>
                        <span className="font-bold text-gray-800">Knowledge Base</span>
                    </div>
                    <div className="h-8 w-8 rounded-full overflow-hidden border border-gray-200">
                        <img src={imgLogo} alt="Logo" className="h-full w-full object-cover" />
                    </div>
                </header>

                <main className="flex-1 overflow-y-auto relative">
                    {/* Content Container */}
                    <div className="max-w-7xl mx-auto p-4 md:p-8 h-full">
                        {children}
                    </div>
                </main>
            </div>
        </div>
    );
};

export default Layout;
