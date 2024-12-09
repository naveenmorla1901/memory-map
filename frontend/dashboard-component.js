// src/components/Dashboard.js
import React, { useState, useEffect } from 'react';
import { useAuth } from '../context/AuthContext';
import authService from '../services/authService';

const Dashboard = () => {
    const { user } = useAuth();
    const [memoryMaps, setMemoryMaps] = useState([]);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState(null);

    useEffect(() => {
        const fetchMemoryMaps = async () => {
            try {
                const response = await fetch('http://localhost:8000/api/memory-maps/', {
                    headers: {
                        ...authService.getAuthHeader()
                    }
                });
                const data = await response.json();
                setMemoryMaps(data);
            } catch (err) {
                setError('Failed to fetch memory maps');
            } finally {
                setLoading(false);
            }
        };

        fetchMemoryMaps();
    }, []);

    if (loading) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-500"></div>
            </div>
        );
    }

    if (error) {
        return (
            <div className="min-h-screen flex items-center justify-center">
                <div className="text-red-500">{error}</div>
            </div>
        );
    }

    return (
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
            <div className="flex justify-between items-center mb-6">
                <h1 className="text-2xl font-bold text-gray-900">Your Memory Maps</h1>
                <button className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-2 rounded-md">
                    Create New Map
                </button>
            </div>

            {memoryMaps.length === 0 ? (
                <div className="text-center py-12">
                    <p className="text-gray-500">No memory maps yet. Create your first one!</p>
                </div>
            ) : (
                <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6">
                    {memoryMaps.map((map) => (
                        <div
                            key={map.id}
                            className="bg-white rounded-lg shadow-md p-6 hover:shadow-lg transition-shadow"
                        >
                            <h3 className="text-lg font-semibold text-gray-900 mb-2">
                                {map.title}
                            </h3>
                            <p className="text-gray-600 mb-4 text-sm">
                                {map.description || 'No description'}
                            </p>
                            <div className="flex justify-between items-center">
                                <span className="text-sm text-gray-500">
                                    {new Date(map.created_at).toLocaleDateString()}
                                </span>
                                <button className="text-blue-600 hover:text-blue-800">
                                    View Details
                                </button>
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </div>
    );
};

export default Dashboard;
