import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
import threading
import queue
import sqlite3
import json
from datetime import datetime
import time
import sys
import traceback


class WebCrawlerApp:
    def __init__(self, root):
        self.root = root
        self.root.title("AI Web Crawler with Ollama")
        self.root.geometry("1200x800")

        # Initialize database
        self.init_database()

        # Thread management
        self.crawl_queue = queue.Queue()
        self.result_queue = queue.Queue()
        self.stop_crawl = threading.Event()
        self.crawl_threads = []

        # Create GUI
        self.create_gui()

        # Start result processor
        self.process_results()

        # Load saved data
        self.load_summaries()

    def init_database(self):
        """Initialize SQLite database"""
        try:
            self.conn = sqlite3.connect('crawler_data.db', check_same_thread=False)
            self.cursor = self.conn.cursor()

            # Create tables
            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS crawled_pages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    url TEXT UNIQUE,
                    title TEXT,
                    content TEXT,
                    crawled_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            self.cursor.execute('''
                CREATE TABLE IF NOT EXISTS summaries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    page_id INTEGER,
                    summary TEXT,
                    analysis TEXT,
                    pinned INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (page_id) REFERENCES crawled_pages(id)
                )
            ''')

            self.conn.commit()
        except Exception as e:
            messagebox.showerror("Database Error", f"Failed to initialize database: {e}")
            sys.exit(1)

    def create_gui(self):
        """Create the GUI layout"""
        # Top frame for controls
        top_frame = ttk.Frame(self.root, padding="10")
        top_frame.pack(fill=tk.X)

        # URL input
        ttk.Label(top_frame, text="Start URL:").pack(side=tk.LEFT, padx=5)
        self.url_entry = ttk.Entry(top_frame, width=50)
        self.url_entry.pack(side=tk.LEFT, padx=5)
        self.url_entry.insert(0, "https://example.com")

        # Thread count
        ttk.Label(top_frame, text="Threads:").pack(side=tk.LEFT, padx=5)
        self.thread_spinbox = ttk.Spinbox(top_frame, from_=1, to=10, width=5)
        self.thread_spinbox.set(3)
        self.thread_spinbox.pack(side=tk.LEFT, padx=5)

        # Max pages
        ttk.Label(top_frame, text="Max Pages:").pack(side=tk.LEFT, padx=5)
        self.max_pages_spinbox = ttk.Spinbox(top_frame, from_=1, to=100, width=5)
        self.max_pages_spinbox.set(10)
        self.max_pages_spinbox.pack(side=tk.LEFT, padx=5)

        # Control buttons
        self.start_btn = ttk.Button(top_frame, text="Start Crawl", command=self.start_crawl)
        self.start_btn.pack(side=tk.LEFT, padx=5)

        self.stop_btn = ttk.Button(top_frame, text="Stop", command=self.stop_crawling, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)

        # Main content area with paned window
        paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Left panel - Crawled URLs
        left_frame = ttk.Frame(paned)
        paned.add(left_frame, weight=1)

        ttk.Label(left_frame, text="Crawled URLs", font=('Arial', 10, 'bold')).pack(pady=5)

        # URL listbox with scrollbar
        url_frame = ttk.Frame(left_frame)
        url_frame.pack(fill=tk.BOTH, expand=True)

        url_scrollbar = ttk.Scrollbar(url_frame)
        url_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.url_listbox = tk.Listbox(url_frame, yscrollcommand=url_scrollbar.set)
        self.url_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.url_listbox.bind('<<ListboxSelect>>', self.on_url_select)
        url_scrollbar.config(command=self.url_listbox.yview)

        # Status label
        self.status_label = ttk.Label(left_frame, text="Status: Ready")
        self.status_label.pack(pady=5)

        # Right panel - Content and AI Analysis
        right_frame = ttk.Frame(paned)
        paned.add(right_frame, weight=2)

        # Notebook for tabs
        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        # Content tab
        content_frame = ttk.Frame(self.notebook)
        self.notebook.add(content_frame, text="Page Content")

        self.content_text = scrolledtext.ScrolledText(content_frame, wrap=tk.WORD, height=15)
        self.content_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # AI Analysis tab
        ai_frame = ttk.Frame(self.notebook)
        self.notebook.add(ai_frame, text="AI Analysis")

        # Ollama controls
        ollama_control_frame = ttk.Frame(ai_frame)
        ollama_control_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(ollama_control_frame, text="Ollama Model:").pack(side=tk.LEFT, padx=5)
        self.model_entry = ttk.Entry(ollama_control_frame, width=20)
        self.model_entry.insert(0, "llama2")
        self.model_entry.pack(side=tk.LEFT, padx=5)

        self.analyze_btn = ttk.Button(ollama_control_frame, text="Analyze with AI", command=self.analyze_content)
        self.analyze_btn.pack(side=tk.LEFT, padx=5)

        self.pin_btn = ttk.Button(ollama_control_frame, text="📌 Pin", command=self.toggle_pin)
        self.pin_btn.pack(side=tk.LEFT, padx=5)

        self.ai_text = scrolledtext.ScrolledText(ai_frame, wrap=tk.WORD, height=15)
        self.ai_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Saved Summaries tab
        saved_frame = ttk.Frame(self.notebook)
        self.notebook.add(saved_frame, text="Saved Summaries")

        # Treeview for summaries
        tree_frame = ttk.Frame(saved_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tree_scroll = ttk.Scrollbar(tree_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.summary_tree = ttk.Treeview(tree_frame, columns=('URL', 'Date', 'Pinned'),
                                         yscrollcommand=tree_scroll.set)
        self.summary_tree.heading('#0', text='ID')
        self.summary_tree.heading('URL', text='URL')
        self.summary_tree.heading('Date', text='Date')
        self.summary_tree.heading('Pinned', text='Pinned')
        self.summary_tree.column('#0', width=50)
        self.summary_tree.column('URL', width=400)
        self.summary_tree.column('Date', width=150)
        self.summary_tree.column('Pinned', width=80)
        self.summary_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.summary_tree.bind('<<TreeviewSelect>>', self.on_summary_select)
        tree_scroll.config(command=self.summary_tree.yview)

        # Summary view
        self.saved_summary_text = scrolledtext.ScrolledText(saved_frame, wrap=tk.WORD, height=10)
        self.saved_summary_text.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Progress bar
        self.progress = ttk.Progressbar(self.root, mode='indeterminate')
        self.progress.pack(fill=tk.X, padx=10, pady=5)

    def crawl_worker(self, max_pages):
        """Worker thread for crawling"""
        visited = set()

        while not self.stop_crawl.is_set() and len(visited) < max_pages:
            try:
                url = self.crawl_queue.get(timeout=1)

                if url in visited:
                    continue

                visited.add(url)

                # Fetch and parse page
                response = requests.get(url, timeout=10, headers={'User-Agent': 'Mozilla/5.0'})
                soup = BeautifulSoup(response.content, 'html.parser')

                # Extract title and content
                title = soup.title.string if soup.title else "No title"

                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()

                text = soup.get_text(separator=' ', strip=True)
                text = ' '.join(text.split())[:5000]  # Limit content length

                # Save to database
                try:
                    self.cursor.execute(
                        'INSERT OR REPLACE INTO crawled_pages (url, title, content) VALUES (?, ?, ?)',
                        (url, title, text)
                    )
                    self.conn.commit()
                except Exception as db_error:
                    print(f"Database error: {db_error}")

                # Send result to GUI
                self.result_queue.put({'type': 'page', 'url': url, 'title': title})

                # Find and queue new links
                base_url = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
                for link in soup.find_all('a', href=True):
                    new_url = urljoin(url, link['href'])
                    if new_url.startswith(base_url) and new_url not in visited:
                        self.crawl_queue.put(new_url)

            except queue.Empty:
                break
            except Exception as e:
                self.result_queue.put({'type': 'error', 'message': f"Error crawling {url}: {str(e)}"})

    def start_crawl(self):
        """Start the crawling process"""
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("Input Error", "Please enter a URL")
            return

        # Validate URL
        if not url.startswith(('http://', 'https://')):
            url = 'https://' + url

        # Clear previous results
        self.url_listbox.delete(0, tk.END)
        self.content_text.delete(1.0, tk.END)
        self.ai_text.delete(1.0, tk.END)

        # Reset stop event
        self.stop_crawl.clear()

        # Queue initial URL
        self.crawl_queue.put(url)

        # Start worker threads
        num_threads = int(self.thread_spinbox.get())
        max_pages = int(self.max_pages_spinbox.get())

        self.crawl_threads = []
        for _ in range(num_threads):
            t = threading.Thread(target=self.crawl_worker, args=(max_pages,), daemon=True)
            t.start()
            self.crawl_threads.append(t)

        # Update UI
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.progress.start()
        self.status_label.config(text="Status: Crawling...")

    def stop_crawling(self):
        """Stop the crawling process"""
        self.stop_crawl.set()
        self.start_btn.config(state=tk.NORMAL)
        self.stop_btn.config(state=tk.DISABLED)
        self.progress.stop()
        self.status_label.config(text="Status: Stopped")

    def process_results(self):
        """Process results from worker threads"""
        try:
            while True:
                result = self.result_queue.get_nowait()

                if result['type'] == 'page':
                    self.url_listbox.insert(tk.END, result['url'])
                    self.status_label.config(text=f"Status: Crawled {self.url_listbox.size()} pages")
                elif result['type'] == 'error':
                    print(result['message'])

        except queue.Empty:
            pass

        # Check if all threads are done
        if self.crawl_threads and all(not t.is_alive() for t in self.crawl_threads):
            if not self.stop_crawl.is_set():
                self.stop_crawling()

        self.root.after(100, self.process_results)

    def on_url_select(self, event):
        """Handle URL selection"""
        selection = self.url_listbox.curselection()
        if not selection:
            return

        url = self.url_listbox.get(selection[0])

        # Load content from database
        self.cursor.execute('SELECT title, content, id FROM crawled_pages WHERE url = ?', (url,))
        result = self.cursor.fetchone()

        if result:
            title, content, page_id = result
            self.content_text.delete(1.0, tk.END)
            self.content_text.insert(1.0, f"Title: {title}\n\n{content}")

            # Store current page_id
            self.current_page_id = page_id

            # Load existing summary if available
            self.cursor.execute('SELECT summary, analysis, pinned FROM summaries WHERE page_id = ?', (page_id,))
            summary_result = self.cursor.fetchone()

            if summary_result:
                summary, analysis, pinned = summary_result
                self.ai_text.delete(1.0, tk.END)
                self.ai_text.insert(1.0, f"Summary:\n{summary}\n\nAnalysis:\n{analysis}")
                self.pin_btn.config(text="📌 Unpin" if pinned else "📌 Pin")
            else:
                self.ai_text.delete(1.0, tk.END)
                self.pin_btn.config(text="📌 Pin")

    def analyze_content(self):
        """Analyze content using Ollama"""
        if not hasattr(self, 'current_page_id'):
            messagebox.showwarning("No Content", "Please select a page first")
            return

        content = self.content_text.get(1.0, tk.END).strip()
        if not content:
            messagebox.showwarning("No Content", "No content to analyze")
            return

        model = self.model_entry.get().strip()

        # Disable button during analysis
        self.analyze_btn.config(state=tk.DISABLED, text="Analyzing...")

        def analyze_thread():
            try:
                # Call Ollama API for summary
                summary_response = requests.post(
                    'http://localhost:11434/api/generate',
                    json={
                        'model': model,
                        'prompt': f"Summarize the following content in 3-5 sentences:\n\n{content[:2000]}",
                        'stream': False
                    },
                    timeout=60
                )

                summary = summary_response.json().get('response', 'No summary generated')

                # Call Ollama API for analysis
                analysis_response = requests.post(
                    'http://localhost:11434/api/generate',
                    json={
                        'model': model,
                        'prompt': f"Analyze the key themes and insights from this content:\n\n{content[:2000]}",
                        'stream': False
                    },
                    timeout=60
                )

                analysis = analysis_response.json().get('response', 'No analysis generated')

                # Save to database
                self.cursor.execute('''
                    INSERT OR REPLACE INTO summaries (page_id, summary, analysis)
                    VALUES (?, ?, ?)
                ''', (self.current_page_id, summary, analysis))
                self.conn.commit()

                # Update GUI
                self.root.after(0, lambda: self.display_analysis(summary, analysis))

            except requests.exceptions.ConnectionError:
                self.root.after(0, lambda: messagebox.showerror(
                    "Connection Error",
                    "Could not connect to Ollama. Make sure Ollama is running on localhost:11434"
                ))
            except Exception as e:
                self.root.after(0, lambda: messagebox.showerror("Error", f"Analysis failed: {str(e)}"))
            finally:
                self.root.after(0, lambda: self.analyze_btn.config(state=tk.NORMAL, text="Analyze with AI"))

        threading.Thread(target=analyze_thread, daemon=True).start()

    def display_analysis(self, summary, analysis):
        """Display AI analysis results"""
        self.ai_text.delete(1.0, tk.END)
        self.ai_text.insert(1.0, f"Summary:\n{summary}\n\nAnalysis:\n{analysis}")
        self.load_summaries()

    def toggle_pin(self):
        """Toggle pin status for current summary"""
        if not hasattr(self, 'current_page_id'):
            return

        self.cursor.execute('SELECT pinned FROM summaries WHERE page_id = ?', (self.current_page_id,))
        result = self.cursor.fetchone()

        if result:
            new_pinned = 0 if result[0] else 1
            self.cursor.execute('UPDATE summaries SET pinned = ? WHERE page_id = ?',
                                (new_pinned, self.current_page_id))
            self.conn.commit()
            self.pin_btn.config(text="📌 Unpin" if new_pinned else "📌 Pin")
            self.load_summaries()
        else:
            messagebox.showinfo("No Summary", "Generate an AI summary first")

    def load_summaries(self):
        """Load all saved summaries"""
        # Clear tree
        for item in self.summary_tree.get_children():
            self.summary_tree.delete(item)

        # Load from database
        self.cursor.execute('''
            SELECT s.id, p.url, s.created_at, s.pinned
            FROM summaries s
            JOIN crawled_pages p ON s.page_id = p.id
            ORDER BY s.pinned DESC, s.created_at DESC
        ''')

        for row in self.cursor.fetchall():
            summary_id, url, created_at, pinned = row
            pinned_text = "📌 Yes" if pinned else "No"
            self.summary_tree.insert('', tk.END, text=str(summary_id),
                                     values=(url[:60] + '...' if len(url) > 60 else url,
                                             created_at, pinned_text))

    def on_summary_select(self, event):
        """Handle summary selection"""
        selection = self.summary_tree.selection()
        if not selection:
            return

        item = self.summary_tree.item(selection[0])
        summary_id = int(item['text'])

        # Load summary
        self.cursor.execute('''
            SELECT s.summary, s.analysis, p.url, p.title
            FROM summaries s
            JOIN crawled_pages p ON s.page_id = p.id
            WHERE s.id = ?
        ''', (summary_id,))

        result = self.cursor.fetchone()
        if result:
            summary, analysis, url, title = result
            self.saved_summary_text.delete(1.0, tk.END)
            self.saved_summary_text.insert(1.0,
                                           f"URL: {url}\nTitle: {title}\n\n" +
                                           f"Summary:\n{summary}\n\nAnalysis:\n{analysis}")

    def __del__(self):
        """Cleanup on exit"""
        try:
            self.conn.close()
        except:
            pass


def main():
    """Main entry point with crash prevention"""
    try:
        root = tk.Tk()
        app = WebCrawlerApp(root)
        root.mainloop()
    except Exception as e:
        print(f"Critical error: {e}")
        traceback.print_exc()
        messagebox.showerror("Critical Error",
                             f"Application crashed: {str(e)}\n\nCheck console for details.")


if __name__ == "__main__":
    main()