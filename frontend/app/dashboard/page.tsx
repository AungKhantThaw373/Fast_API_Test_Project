'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

interface User {
    id: string;
    email: string;
    created_at: string;
}

export default function DashboardPage() {
    const router = useRouter();
    const [users, setUsers] = useState<User[]>([]);
    const [currentUser, setCurrentUser] = useState<string | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState('');

    useEffect(() => {
        const fetchData = async () => {
            try {
                // First, verify user is authenticated by trying to fetch current user info
                const currentUserRes = await fetch('http://localhost:8000/api/py/me', {
                    credentials: 'include',
                });

                if (!currentUserRes.ok) {
                    // Not authenticated, redirect to login
                    router.push('/login');
                    return;
                }

                const currentUserData = await currentUserRes.json();
                setCurrentUser(currentUserData.username);

                // Fetch all users
                const usersRes = await fetch('http://localhost:8000/api/py/users', {
                    credentials: 'include',
                });

                if (!usersRes.ok) {
                    throw new Error('Failed to fetch users');
                }

                const usersData = await usersRes.json();
                setUsers(usersData.users);
            } catch (err) {
                console.error('Error fetching data:', err);
                setError('Failed to load dashboard data');
                // If fetch fails, redirect to login
                setTimeout(() => router.push('/login'), 1000);
            } finally {
                setLoading(false);
            }
        };

        fetchData();
    }, [router]);

    const handleLogout = async () => {
        try {
            // Call logout endpoint if it exists, or just clear cookies
            await fetch('http://localhost:8000/api/py/logout', {
                method: 'POST',
                credentials: 'include',
            }).catch(() => {
                // Logout endpoint might not exist, that's okay
            });

            // Redirect to login
            router.push('/login');
        } catch (err) {
            console.error('Logout error:', err);
            router.push('/login');
        }
    };

    if (loading) {
        return (
            <div style={styles.container}>
                <div style={styles.center}>Loading...</div>
            </div>
        );
    }

    return (
        <div style={styles.container}>
            <div style={styles.header}>
                <h1 style={styles.title}>Dashboard</h1>
                <div style={styles.userInfo}>
                    {currentUser && <span>Welcome, {currentUser}</span>}
                    <button onClick={handleLogout} style={styles.logoutButton}>
                        Logout
                    </button>
                </div>
            </div>

            <div style={styles.content}>
                {error && <div style={styles.error}>{error}</div>}

                <div style={styles.section}>
                    <h2 style={styles.sectionTitle}>Users</h2>
                    {users.length === 0 ? (
                        <p style={styles.noData}>No users found</p>
                    ) : (
                        <div style={styles.table}>
                            <div style={styles.tableHeader}>
                                <div style={styles.tableCell}>ID</div>
                                <div style={styles.tableCell}>Email</div>
                                <div style={styles.tableCell}>Created At</div>
                            </div>
                            {users.map((user) => (
                                <div key={user.id} style={styles.tableRow}>
                                    <div style={styles.tableCell}>{user.id.substring(0, 8)}...</div>
                                    <div style={styles.tableCell}>{user.email}</div>
                                    <div style={styles.tableCell}>
                                        {new Date(user.created_at).toLocaleDateString()}
                                    </div>
                                </div>
                            ))}
                        </div>
                    )}
                </div>
            </div>
        </div>
    );
}

const styles = {
    container: {
        minHeight: '100vh',
        backgroundColor: '#f5f5f5',
        fontFamily: 'Arial, sans-serif',
    },
    center: {
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        fontSize: '18px',
        color: '#666',
    },
    header: {
        backgroundColor: 'white',
        padding: '20px 40px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
        boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
    },
    title: {
        margin: 0,
        fontSize: '28px',
        color: '#333',
    },
    userInfo: {
        display: 'flex',
        alignItems: 'center',
        gap: '20px',
        fontSize: '14px',
        color: '#666',
    },
    logoutButton: {
        padding: '8px 16px',
        fontSize: '14px',
        fontWeight: 'bold' as const,
        color: 'white',
        backgroundColor: '#dc3545',
        border: 'none',
        borderRadius: '4px',
        cursor: 'pointer',
    },
    content: {
        padding: '40px',
        maxWidth: '1200px',
        margin: '0 auto',
    },
    error: {
        padding: '15px',
        backgroundColor: '#f8d7da',
        color: '#721c24',
        borderRadius: '4px',
        marginBottom: '20px',
        border: '1px solid #f5c6cb',
    },
    section: {
        backgroundColor: 'white',
        padding: '20px',
        borderRadius: '8px',
        boxShadow: '0 2px 4px rgba(0, 0, 0, 0.1)',
    },
    sectionTitle: {
        marginTop: 0,
        marginBottom: '20px',
        fontSize: '20px',
        color: '#333',
    },
    noData: {
        color: '#999',
        fontStyle: 'italic',
        textAlign: 'center' as const,
    },
    table: {
        display: 'flex',
        flexDirection: 'column' as const,
        gap: '0',
        border: '1px solid #ddd',
        borderRadius: '4px',
        overflow: 'hidden',
    },
    tableHeader: {
        display: 'grid',
        gridTemplateColumns: '1fr 2fr 2fr',
        backgroundColor: '#f9f9f9',
        fontWeight: 'bold' as const,
        borderBottom: '2px solid #ddd',
    },
    tableRow: {
        display: 'grid',
        gridTemplateColumns: '1fr 2fr 2fr',
        borderBottom: '1px solid #ddd',
        '&:lastChild': {
            borderBottom: 'none',
        },
    },
    tableCell: {
        padding: '12px',
        color: '#333',
        fontSize: '14px',
    },
};
