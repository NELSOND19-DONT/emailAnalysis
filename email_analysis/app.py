import json
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from core import Store

class App:
    def __init__(self, root):
        self.store = Store()
        self.root = root
        self.busy = False
        root.title('Email Analysis — offline')
        root.geometry('1200x800')
        toolbar = ttk.Frame(root); toolbar.pack(fill='x', padx=8, pady=8)
        for label, command in [('Import Gmail (read-only)', self.gmail), ('Import EML / MBOX', self.import_files), ('Analysis', self.analysis), ('Evaluate labels', self.evaluate), ('Export label template', self.labels), ('Delete imported data', self.delete)]:
            ttk.Button(toolbar, text=label, command=command).pack(side='left', padx=4)
        filters = ttk.Frame(root); filters.pack(fill='x', padx=8)
        self.filters = {}
        for name in ['Search', 'Sender', 'Category', 'From YYYY-MM-DD', 'To YYYY-MM-DD']:
            ttk.Label(filters, text=name).pack(side='left')
            v = tk.StringVar(); self.filters[name] = v
            if name == 'Category':
                ttk.Combobox(filters, textvariable=v, values=['', 'Uncategorized', *self.store.config['categories']], width=15, state='readonly').pack(side='left')
            else:
                ttk.Entry(filters, textvariable=v, width=17).pack(side='left')
        self.review = tk.BooleanVar()
        ttk.Checkbutton(root, text='Only classifications needing review', variable=self.review, command=self.refresh).pack(anchor='w', padx=8)
        ttk.Button(root, text='Apply filters', command=self.refresh).pack(anchor='w', padx=8)
        self.tree = ttk.Treeview(root, columns=('date', 'sender', 'subject', 'categories', 'review'), show='headings', height=14)
        for c in self.tree['columns']:
            self.tree.heading(c, text=c.title()); self.tree.column(c, width=180 if c != 'subject' else 350)
        self.tree.pack(fill='both', expand=True, padx=8)
        self.tree.bind('<<TreeviewSelect>>', self.show_email)
        correction = ttk.Frame(root); correction.pack(fill='x', padx=8, pady=5)
        ttk.Label(correction, text='Correct categories (comma separated):').pack(side='left')
        self.correction = tk.StringVar()
        ttk.Entry(correction, textvariable=self.correction, width=50).pack(side='left')
        ttk.Button(correction, text='Save correction', command=self.correct).pack(side='left')
        self.detail = tk.Text(root, height=17, wrap='word', state='disabled'); self.detail.pack(fill='both', expand=True, padx=8, pady=8)
        self.status = tk.StringVar(); ttk.Label(root, textvariable=self.status).pack(anchor='w', padx=8)
        self.refresh()

    def refresh(self):
        f = self.filters
        self.rows = self.store.emails(f['Search'].get(), f['Category'].get(), f['Sender'].get(), f['From YYYY-MM-DD'].get(), f['To YYYY-MM-DD'].get(), self.review.get())
        self.tree.delete(*self.tree.get_children())
        for r in self.rows:
            self.tree.insert('', 'end', iid=r['id'], values=(r['date'][:10], r['sender'], r['subject'], ', '.join(r['categories']), 'Review' if r['review'] else ''))
        self.status.set(f"{len(self.rows)} emails · {len({r['thread'] for r in self.rows})} estimated threads")

    def selected(self):
        selection = self.tree.selection()
        return next((r for r in self.rows if selection and r['id'] == selection[0]), None)

    def show_email(self, event=None):
        r = self.selected()
        if not r: return
        self.correction.set(', '.join(r['categories']))
        content = f"{r['subject']}\nFrom: {r['sender']}\nDate: {r['date'] or 'Unknown'}\nID: {r['id']}\n\n{r['explanation']}\n\nPossible actions (verify before acting):\n" + json.dumps(r['actions'], indent=2) + '\n\n' + r['body']
        self.detail.configure(state='normal'); self.detail.delete('1.0', 'end'); self.detail.insert('1.0', content); self.detail.configure(state='disabled')

    def import_files(self):
        if self.busy: return
        paths = filedialog.askopenfilenames(filetypes=[('Email exports', '*.eml *.mbox')])
        if paths:
            try:
                result = self.store.import_files(paths)
                self.refresh(); messagebox.showinfo('Import results', json.dumps(result, indent=2))
            except Exception as e:
                messagebox.showerror('Import failed', str(e))

    def gmail(self):
        if self.busy: return
        self.busy = True
        events = queue.Queue()
        self.status.set('Signing in / importing Gmail read-only…')
        def worker():
            store = None
            try:
                store = Store(config=self.store.config)
                from gmail_import import import_gmail
                result = import_gmail(store, progress=lambda result: events.put(('progress', result)))
                events.put(('done', result))
            except Exception as e:
                events.put(('error', str(e)))
            finally:
                if store is not None: store.db.close()
        threading.Thread(target=worker, daemon=True).start()
        def poll():
            while not events.empty():
                kind, value = events.get_nowait()
                if kind == 'progress':
                    self.status.set(f"Gmail: examined {value['examined']}, imported {value['added']}, duplicates {value['duplicates']}")
                else:
                    self.busy = False; self.refresh()
                    if kind == 'done': messagebox.showinfo('Gmail import results', json.dumps(value, indent=2))
                    else: messagebox.showerror('Gmail import failed', value + '\nCompleted imports are retained; retry safely.')
                    return
            self.root.after(200, poll)
        poll()

    def correct(self):
        r = self.selected()
        if r:
            try:
                self.store.correct(r['id'], [c.strip() for c in self.correction.get().split(',') if c.strip()]); self.refresh()
            except ValueError as e: messagebox.showerror('Invalid categories', str(e))

    def analysis(self):
        report = self.store.analysis(self.rows)
        window = tk.Toplevel(self.root); window.title('Analysis of filtered emails'); window.geometry('900x650')
        text = tk.Text(window, wrap='word'); text.pack(fill='both', expand=True)
        text.insert('end', f"{report['emails']} emails; {report['threads']} estimated threads\nCategory counts overlap when multiple categories apply.\nSummaries are supporting excerpts, not AI summaries.\n\n")
        for category, data in report['categories'].items():
            text.insert('end', f"{category}: {data['emails']} emails, {data['threads']} threads\nCommon senders: {data['common_senders']}\nMonthly trend: {data['months']}\n")
            for s in data['summary']:
                tag = 'email_' + s['email_id']
                text.insert('end', s['subject'] or '(no subject)', tag)
                text.tag_config(tag, foreground='blue', underline=True)
                text.tag_bind(tag, '<Button-1>', lambda event, identity=s['email_id']: self.open_support(identity, window))
                text.insert('end', '\n' + s['excerpt'] + '\n')
            text.insert('end', '\n')
        text.insert('end', 'Possible action items:\n')
        for a in report['possible_actions']:
            tag = 'email_' + a['email_id']
            text.insert('end', f"[{a['kind']}: {a['date'] or 'no date'}] {a['text']}\n", tag)
            text.tag_config(tag, foreground='blue', underline=True)
            text.tag_bind(tag, '<Button-1>', lambda event, identity=a['email_id']: self.open_support(identity, window))
        text.configure(state='disabled')

    def open_support(self, identity, window):
        self.tree.selection_set(identity); self.tree.see(identity); self.show_email(); window.destroy()

    def labels(self):
        path = filedialog.asksaveasfilename(initialdir=str(__import__('core').ROOT / 'private'), initialfile='labels.json', defaultextension='.json')
        if path:
            with open(path, 'w', encoding='utf-8') as f: json.dump({r['id']: [] for r in self.rows}, f, indent=2)

    def evaluate(self):
        path = filedialog.askopenfilename(filetypes=[('Labels JSON', '*.json')])
        if path:
            try:
                with open(path, encoding='utf-8') as f: report = self.store.evaluate(json.load(f))
                messagebox.showinfo('Evaluation of automatic classifications', json.dumps(report, indent=2))
            except (ValueError, TypeError, OSError) as e: messagebox.showerror('Evaluation failed', str(e))

    def delete(self):
        if self.busy:
            messagebox.showinfo('Import running', 'Wait for Gmail import to finish before deleting data.'); return
        if messagebox.askyesno('Delete data', 'Permanently delete all imported emails and corrections from this app? Original export files remain.'):
            self.store.delete_all(); self.refresh()
            self.detail.configure(state='normal'); self.detail.delete('1.0', 'end'); self.detail.configure(state='disabled')

if __name__ == '__main__':
    root = tk.Tk(); App(root); root.mainloop()
