'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';

export default function LoginPage() {
    const router = useRouter();
    const [email, setEmail] = useState('');
    const [password, setPassword] = useState('');
    const [error, setError] = useState('');
    const [loading, setLoading] = useState(false);
    const [showSignUp, setShowSignUp] = useState(false);
    const [signUpData, setSignUpData] = useState({
        username: '',
        email: '',
        password: '',
    });
    const [signUpError, setSignUpError] = useState('');
    const [signUpLoading, setSignUpLoading] = useState(false);

    // Check if already logged in
    useEffect(() => {
        const checkAuth = async () => {
            try {
                const response = await fetch('http://localhost:8000/api/py/me', {
                    credentials: 'include',
                });
                if (response.ok) {
                    router.push('/dashboard');
                }
            } catch (err) {
                // Not authenticated, stay on login
            }
        };
        checkAuth();
    }, [router]);

    const handleLogin = async (e: React.FormEvent) => {
        e.preventDefault();
        setError('');
        setLoading(true);

        try {
            const formData = new FormData();
            formData.append('username', email);
            formData.append('password', password);

            const response = await fetch('http://localhost:8000/api/py/token', {
                method: 'POST',
                credentials: 'include',
                body: formData,
            });

            if (!response.ok) {
                const data = await response.json();
                setError(data.detail || 'Login failed');
                setLoading(false);
                return;
            }

            const data = await response.json();
            if (data.access_token) {
                router.push('/dashboard');
            }
        } catch (err) {
            setError('An error occurred. Please try again.');
            setLoading(false);
        }
    };

    const handleSignUp = async (e: React.FormEvent) => {
        e.preventDefault();
        setSignUpError('');
        setSignUpLoading(true);

        try {
            const response = await fetch('http://localhost:8000/api/py/register', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(signUpData),
            });

            if (!response.ok) {
                const data = await response.json();
                setSignUpError(data.detail || 'Sign up failed');
                setSignUpLoading(false);
                return;
            }

            // Sign up successful, switch back to login
            setShowSignUp(false);
            setSignUpData({ username: '', email: '', password: '' });
            setError('');
            setEmail(signUpData.email);
            setPassword('');
            alert('Sign up successful! Please log in.');
        } catch (err) {
            setSignUpError('An error occurred. Please try again.');
            setSignUpLoading(false);
        }
    };

    return (
        <div style={styles.container}>
            <div style={styles.box}>
                <h1 style={styles.title}>{showSignUp ? 'Sign Up' : 'Login'}</h1>

                {!showSignUp ? (
                    // Login Form
                    <form onSubmit={handleLogin} style={styles.form}>
                        {error && <div style={styles.error}>{error}</div>}

                        <div style={styles.formGroup}>
                            <label style={styles.label}>Email</label>
                            <input
                                type="email"
                                value={email}
                                onChange={(e) => setEmail(e.target.value)}
                                required
                                style={styles.input}
                                placeholder="Enter your email"
                            />
                        </div>

                        <div style={styles.formGroup}>
                            <label style={styles.label}>Password</label>
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                required
                                style={styles.input}
                                placeholder="Enter your password"
                            />
                        </div>

                        <button type="submit" disabled={loading} style={styles.button}>
                            {loading ? 'Logging in...' : 'Login'}
                        </button>

                        <p style={styles.switchText}>
                            Don't have an account?{' '}
                            <button
                                type="button"
                                onClick={() => setShowSignUp(true)}
                                style={styles.switchLink}
                            >
                                Sign up
                            </button>
                        </p>
                    </form>
                ) : (
                    // Sign Up Form
                    <form onSubmit={handleSignUp} style={styles.form}>
                        {signUpError && <div style={styles.error}>{signUpError}</div>}

                        <div style={styles.formGroup}>
                            <label style={styles.label}>Username</label>
                            <input
                                type="text"
                                value={signUpData.username}
                                onChange={(e) =>
                                    setSignUpData({ ...signUpData, username: e.target.value })
                                }
                                required
                                style={styles.input}
                                placeholder="Choose a username"
                            />
                        </div>

                        <div style={styles.formGroup}>
                            <label style={styles.label}>Email</label>
                            <input
                                type="email"
                                value={signUpData.email}
                                onChange={(e) =>
                                    setSignUpData({ ...signUpData, email: e.target.value })
                                }
                                required
                                style={styles.input}
                                placeholder="Enter your email"
                            />
                        </div>

                        <div style={styles.formGroup}>
                            <label style={styles.label}>Password</label>
                            <input
                                type="password"
                                value={signUpData.password}
                                onChange={(e) =>
                                    setSignUpData({ ...signUpData, password: e.target.value })
                                }
                                required
                                style={styles.input}
                                placeholder="Enter a password"
                            />
                        </div>

                        <button type="submit" disabled={signUpLoading} style={styles.button}>
                            {signUpLoading ? 'Creating account...' : 'Sign Up'}
                        </button>

                        <p style={styles.switchText}>
                            Already have an account?{' '}
                            <button
                                type="button"
                                onClick={() => setShowSignUp(false)}
                                style={styles.switchLink}
                            >
                                Login
                            </button>
                        </p>
                    </form>
                )}
            </div>
        </div>
    );
}

const styles = {
    container: {
        display: 'flex',
        justifyContent: 'center',
        alignItems: 'center',
        minHeight: '100vh',
        backgroundColor: '#f5f5f5',
        fontFamily: 'Arial, sans-serif',
    },
    box: {
        width: '100%',
        maxWidth: '400px',
        padding: '40px',
        backgroundColor: 'white',
        borderRadius: '8px',
        boxShadow: '0 2px 10px rgba(0, 0, 0, 0.1)',
    },
    title: {
        textAlign: 'center' as const,
        marginBottom: '30px',
        fontSize: '24px',
        color: '#333',
    },
    form: {
        display: 'flex',
        flexDirection: 'column' as const,
        gap: '20px',
    },
    formGroup: {
        display: 'flex',
        flexDirection: 'column' as const,
        gap: '8px',
    },
    label: {
        fontSize: '14px',
        fontWeight: 'bold' as const,
        color: '#555',
    },
    input: {
        padding: '10px',
        fontSize: '14px',
        border: '1px solid #ddd',
        borderRadius: '4px',
        boxSizing: 'border-box' as const,
    },
    button: {
        padding: '12px',
        fontSize: '16px',
        fontWeight: 'bold' as const,
        color: 'white',
        backgroundColor: '#007bff',
        border: 'none',
        borderRadius: '4px',
        cursor: 'pointer',
        marginTop: '10px',
    },
    error: {
        padding: '10px',
        backgroundColor: '#f8d7da',
        color: '#721c24',
        borderRadius: '4px',
        fontSize: '14px',
        border: '1px solid #f5c6cb',
    },
    switchText: {
        textAlign: 'center' as const,
        fontSize: '14px',
        color: '#666',
    },
    switchLink: {
        background: 'none',
        border: 'none',
        color: '#007bff',
        cursor: 'pointer',
        textDecoration: 'underline',
        fontSize: '14px',
        padding: 0,
    },
};
