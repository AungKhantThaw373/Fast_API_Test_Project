'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useCallback, useEffect, useMemo, useState, type ChangeEvent, type FormEvent } from 'react';
import { api, type CurrentUser, type DraftFile, type DraftFolder } from '@/lib/api';
import { isUnauthorized } from '@/lib/auth-redirect';

function formatSize(bytes: number) {
	if (bytes < 1024) return `${bytes} B`;
	if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)} KB`;
	return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value: string) {
	return new Date(value).toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' });
}

export default function EditingLibraryPage() {
	const router = useRouter();
	const [user, setUser] = useState<CurrentUser | null>(null);
	const [folders, setFolders] = useState<DraftFolder[]>([]);
	const [files, setFiles] = useState<DraftFile[]>([]);
	const [selectedFolderId, setSelectedFolderId] = useState('all');
	const [newFolderName, setNewFolderName] = useState('');
	const [loading, setLoading] = useState(true);
	const [uploading, setUploading] = useState(false);
	const [error, setError] = useState('');
	const [notice, setNotice] = useState('');
	const [preview, setPreview] = useState<DraftFile | null>(null);
	const [fileSearch, setFileSearch] = useState('');
	const [fileSort, setFileSort] = useState<'updated' | 'name' | 'size'>('updated');

	const loadLibrary = useCallback(async () => {
		const [account, folderList, fileList] = await Promise.all([api.me(), api.editingFolders(), api.draftFiles()]);
		setUser(account);
		setFolders(folderList);
		setFiles(fileList);
	}, []);

	useEffect(() => {
		let active = true;
		Promise.all([api.me(), api.editingFolders(), api.draftFiles()]).then(([account, folderList, fileList]) => {
			if (!active) return;
			setUser(account);
			setFolders(folderList);
			setFiles(fileList);
		}).catch((cause: unknown) => {
			if (!active) return;
			if (isUnauthorized(cause)) return;
			setError(cause instanceof Error ? cause.message : 'Your draft library could not be opened.');
		}).finally(() => { if (active) setLoading(false); });
		return () => { active = false; };
	}, [router]);

	useEffect(() => {
		if (!preview) return;
		const closeOnEscape = (event: KeyboardEvent) => { if (event.key === 'Escape') setPreview(null); };
		window.addEventListener('keydown', closeOnEscape);
		return () => window.removeEventListener('keydown', closeOnEscape);
	}, [preview]);

	const visibleFiles = useMemo(() => {
		const query = fileSearch.trim().toLocaleLowerCase();
		return (selectedFolderId === 'all' ? files : files.filter((file) => file.folder_id === selectedFolderId))
			.filter((file) => !query || `${file.title} ${file.original_filename}`.toLocaleLowerCase().includes(query))
			.sort((a, b) => fileSort === 'name' ? a.title.localeCompare(b.title) : fileSort === 'size' ? b.size_bytes - a.size_bytes : b.updated_at.localeCompare(a.updated_at));
	}, [files, selectedFolderId, fileSearch, fileSort]);
	const selectedFolder = folders.find((folder) => folder.id === selectedFolderId);

	async function uploadFiles(event: ChangeEvent<HTMLInputElement>) {
		const selected = Array.from(event.target.files ?? []);
		event.target.value = '';
		if (!selected.length) return;
		const destination = selectedFolderId === 'all'
			? folders.find((folder) => folder.name.toLocaleLowerCase() === 'unsorted')?.id
			: selectedFolderId;
		if (!destination) {
			setError('Create or select a folder before uploading drafts.');
			return;
		}
		setUploading(true); setError(''); setNotice('');
		let uploaded = 0;
		try {
			for (const file of selected) {
				await api.uploadDraftFile(file, destination);
				uploaded += 1;
			}
			await loadLibrary();
			setNotice(`${uploaded} ${uploaded === 1 ? 'draft was' : 'drafts were'} added to your library.`);
		} catch (cause) {
			await loadLibrary().catch(() => undefined);
			const detail = cause instanceof Error ? cause.message : 'The selected files could not be uploaded.';
			setError(uploaded ? `${uploaded} file${uploaded === 1 ? '' : 's'} uploaded before the next file failed. ${detail}` : detail);
		} finally { setUploading(false); }
	}

	async function createFolder(event: FormEvent<HTMLFormElement>) {
		event.preventDefault();
		if (!newFolderName.trim()) return;
		try {
			const folder = await api.createEditingFolder(newFolderName.trim());
			setNewFolderName('');
			setSelectedFolderId(folder.id);
			await loadLibrary();
			setNotice(`Folder “${folder.name}” created.`);
			setError('');
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'That folder could not be created.'); }
	}

	async function renameFolder(folder: DraftFolder) {
		const name = window.prompt('Rename folder', folder.name)?.trim();
		if (!name || name === folder.name) return;
		try {
			await api.renameEditingFolder(folder.id, name);
			await loadLibrary();
			setError('');
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'That folder could not be renamed.'); }
	}

	async function deleteFolder(folder: DraftFolder) {
		if (!window.confirm(`Remove the empty folder “${folder.name}”?`)) return;
		try {
			await api.deleteEditingFolder(folder.id);
			if (selectedFolderId === folder.id) setSelectedFolderId('all');
			await loadLibrary();
			setError('');
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'That folder could not be removed.'); }
	}

	async function renameFile(file: DraftFile) {
		const title = window.prompt('Rename draft', file.title)?.trim();
		if (!title || title === file.title) return;
		try {
			const updated = await api.updateDraftFile(file.id, { title });
			setFiles((current) => current.map((item) => item.id === updated.id ? updated : item));
			setError('');
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'That draft could not be renamed.'); }
	}

	async function moveFile(file: DraftFile, folderId: string) {
		if (folderId === file.folder_id) return;
		try {
			const updated = await api.updateDraftFile(file.id, { folder_id: folderId });
			setFiles((current) => current.map((item) => item.id === updated.id ? updated : item));
			setFolders(await api.editingFolders());
			setError('');
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'That draft could not be moved.'); }
	}

	async function removeFile(file: DraftFile) {
		if (!window.confirm(`Remove “${file.original_filename}” from your library? This deletes the stored copy.`)) return;
		try {
			await api.deleteDraftFile(file.id);
			setFiles((current) => current.filter((item) => item.id !== file.id));
			setFolders(await api.editingFolders());
			if (preview?.id === file.id) setPreview(null);
			setError('');
		} catch (cause) { setError(cause instanceof Error ? cause.message : 'That draft could not be removed.'); }
	}

	async function logout() {
		try { await api.logout(); } finally { router.replace('/login'); }
	}

	if (loading) return <main className="quiet-loading"><span className="loading-mark" /><p>Opening your draft library…</p></main>;

	return (
		<main className="library-page">
			<header className="library-header">
				<div className="app-header-left">
					<Link className="wordmark" href="/dashboard"><span className="wordmark-icon">s</span>stillroom</Link>
					<nav className="product-nav" aria-label="Workspace">
						<Link href="/dashboard">Writing</Link>
						<Link href="/editing" aria-current="page">Editing</Link>
						<Link href="/settings">Settings</Link>
					</nav>
				</div>
				<div className="header-account"><span>{user?.username}</span><button className="quiet-button" onClick={() => void logout()}>Sign out</button></div>
			</header>
			<section className="library-content editing-library">
				<div className="welcome-block"><div className="eyebrow">EDITING FILES</div><h1>Your drafts, in one place.</h1><p>Upload and organize the files you are working on. This is a file library, not an in-app writing editor. Files here are stored as-is and are not added to Writing’s continuity memory.</p></div>
				{error && <div className="notice" role="alert">{error}</div>}
				{notice && <div className="editing-notice" role="status">{notice}<button aria-label="Dismiss message" onClick={() => setNotice('')}>×</button></div>}
				<div className="editing-layout">
					<aside className="folder-sidebar" aria-label="Draft folders">
						<div className="folder-sidebar-heading"><span>FOLDERS</span><span>{folders.length}</span></div>
						<button className={'folder-choice' + (selectedFolderId === 'all' ? ' selected' : '')} onClick={() => setSelectedFolderId('all')}><span>All drafts</span><span>{files.length}</span></button>
						{folders.map((folder) => <div className="folder-row" key={folder.id}>
							<button className={'folder-choice' + (selectedFolderId === folder.id ? ' selected' : '')} onClick={() => setSelectedFolderId(folder.id)}><span>▱ {folder.name}</span><span>{folder.file_count}</span></button>
							{folder.name.toLocaleLowerCase() !== 'unsorted' && <div className="folder-actions"><button onClick={() => void renameFolder(folder)} aria-label={`Rename ${folder.name}`}>Rename</button><button onClick={() => void deleteFolder(folder)} aria-label={`Remove ${folder.name}`}>Remove</button></div>}
						</div>)}
						<form className="folder-create" onSubmit={createFolder}><input value={newFolderName} onChange={(event) => setNewFolderName(event.target.value)} placeholder="New folder" aria-label="New folder name" maxLength={100} /><button type="submit" disabled={!newFolderName.trim()} aria-label="Create folder">+</button></form>
						<p className="folder-storage-note">Files are private to your account and stored with your Stillroom library. They are not indexed for AI analysis.</p>
					</aside>
					<section className="drafts-panel">
						<div className="drafts-panel-heading"><div><div className="eyebrow">{selectedFolder ? 'FOLDER' : 'YOUR FILES'}</div><h2>{selectedFolder?.name ?? 'All drafts'}</h2></div><span>{visibleFiles.length} {visibleFiles.length === 1 ? 'file' : 'files'}</span></div>
						<div className="draft-library-tools"><input value={fileSearch} onChange={(event) => setFileSearch(event.target.value)} placeholder="Search drafts" aria-label="Search draft files" /><label>Sort<select value={fileSort} onChange={(event) => setFileSort(event.target.value as typeof fileSort)}><option value="updated">Recently updated</option><option value="name">Name</option><option value="size">Largest first</option></select></label></div>
						<label className={'upload-dropzone' + (uploading ? ' uploading' : '')}>
							<span className="upload-mark">↑</span><span className="upload-copy"><strong>{uploading ? 'Uploading your files…' : 'Add story draft files'}</strong><small>{selectedFolder ? `New uploads go to ${selectedFolder.name}.` : 'New uploads go to Unsorted. Choose one or more files.'}</small></span>
							<span className="button button-primary">{uploading ? 'Please wait…' : 'Choose files'}</span>
							<input type="file" multiple disabled={uploading} accept=".pdf,.doc,.docx,.odt,.rtf,.txt,.md,.markdown,application/pdf,text/plain" onChange={(event) => void uploadFiles(event)} />
							<small className="upload-limits">PDF, Word, OpenDocument, RTF, TXT, or Markdown · up to 25 MB each</small>
						</label>
						{visibleFiles.length ? <div className="draft-file-list" role="list">
							{visibleFiles.map((file) => <article className="draft-file-card" key={file.id} role="listitem">
								<div className="draft-file-icon">{file.extension.replace('.', '').slice(0, 4).toUpperCase()}</div>
								<div className="draft-file-main"><div className="draft-file-name"><strong>{file.title}</strong><span>{file.original_filename}</span></div><div className="draft-file-meta"><span>{file.folder_name}</span><span>{formatSize(file.size_bytes)}</span><time>{formatDate(file.created_at)}</time></div></div>
								<div className="draft-file-actions">
									{file.previewable && <button className="text-button" onClick={() => setPreview(file)}>Preview</button>}
									<a className="text-button" href={api.draftFileContentUrl(file.id)}>Download</a>
									<select aria-label={`Move ${file.title}`} value={file.folder_id} onChange={(event) => void moveFile(file, event.target.value)}>{folders.map((folder) => <option value={folder.id} key={folder.id}>{folder.name}</option>)}</select>
									<button className="text-button subtle" onClick={() => void renameFile(file)}>Rename</button>
									<button className="text-button subtle" onClick={() => void removeFile(file)}>Remove</button>
								</div>
							</article>)}
						</div> : <div className="editing-empty"><span>▱</span><h3>No drafts in this folder yet.</h3><p>Upload a manuscript file to keep it organized here.</p></div>}
					</section>
				</div>
				<footer className="library-footer">Your files stay yours. Stillroom does not edit or rewrite these uploads.</footer>
			</section>
			{preview && <div className="preview-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setPreview(null); }}><section className="draft-preview" role="dialog" aria-modal="true" aria-label={`Preview ${preview.title}`}><header><div><strong>{preview.title}</strong><span>{preview.original_filename}</span></div><button className="quiet-button" onClick={() => setPreview(null)}>Close</button></header><iframe title={`Read-only preview of ${preview.title}`} src={api.draftFileContentUrl(preview.id, true)} referrerPolicy="no-referrer" sandbox="allow-same-origin" /></section></div>}
		</main>
	);
}
