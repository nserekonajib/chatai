 // Global variables
 let currentChatId = null;
 let isTyping = false;
 let eventSource = null;

 // Initialize the application
 document.addEventListener('DOMContentLoaded', function() {
     setupEventListeners();
     loadChatHistory();
 });

 // Set up all event listeners
 function setupEventListeners() {
     // Sidebar toggle
     document.getElementById('sidebarToggle').addEventListener('click', function() {
         const sidebar = document.getElementById('sidebar');
         sidebar.classList.toggle('sidebar-open');
         document.getElementById('sidebarBackdrop').style.display = sidebar.classList.contains('sidebar-open') ? 'block' : 'none';
     });

     // Sidebar backdrop click
     document.getElementById('sidebarBackdrop').addEventListener('click', function() {
         document.getElementById('sidebar').classList.remove('sidebar-open');
         this.style.display = 'none';
     });

     // New chat button
     document.getElementById('newChatBtn').addEventListener('click', startNewChat);

     // Logout button
     document.getElementById('logoutBtn').addEventListener('click', logout);

     // Message input
     const messageInput = document.getElementById('messageInput');
     messageInput.addEventListener('input', function() {
         this.style.height = 'auto';
         this.style.height = Math.min(this.scrollHeight, 150) + 'px';
     });

     // Send message on Enter (but not Shift+Enter)
     messageInput.addEventListener('keydown', function(e) {
         if (e.key === 'Enter' && !e.shiftKey) {
             e.preventDefault();
             sendMessage();
         }
     });

     // Send button
     document.getElementById('sendButton').addEventListener('click', sendMessage);

     // PDF upload
     document.getElementById('pdfUpload').addEventListener('change', handlePdfUpload);

     // Remove PDF
     document.getElementById('removePdf').addEventListener('click', function() {
         document.getElementById('pdfIndicator').classList.add('hidden');
         // Here you would also remove the PDF from the session
         fetch('/remove-pdf', {
             method: 'POST',
             headers: {
                 'Content-Type': 'application/json',
             },
             body: JSON.stringify({})
         }).then(response => response.json())
         .then(data => {
             if (data.success) {
                 addSystemMessage('PDF removed successfully');
             }
         });
     });
 }

 // Load chat history from server
 async function loadChatHistory() {
     try {
         const response = await fetch('/chats');
         const data = await response.json();
         
         if (data.success && data.chats) {
             const chatHistory = document.getElementById('chatHistory');
             chatHistory.innerHTML = '';
             
             data.chats.forEach(chat => {
                 const chatItem = document.createElement('div');
                 chatItem.className = 'chat-item px-3 py-2 rounded-md cursor-pointer';
                 chatItem.dataset.chatId = chat.id;
                 
                 chatItem.innerHTML = `
                     <div class="flex justify-between items-center">
                         <span class="text-sm truncate">${chat.title}</span>
                         <span class="text-xs text-gray-400">${formatDate(chat.created_at)}</span>
                     </div>
                 `;

                 const deleteBtn = document.createElement('button');
                 deleteBtn.className = 'ml-2 text-red-400 hover:text-red-600 text-xs';
                 deleteBtn.innerHTML = '<i class="fas fa-trash"></i>';
                 deleteBtn.title = 'Delete chat';
                 deleteBtn.onclick = async (e) => {
                     e.stopPropagation();
                     if (confirm('Delete this chat and all its messages?')) {
                         await fetch('/delete-chat', {
                             method: 'POST',
                             headers: { 'Content-Type': 'application/json' },
                             body: JSON.stringify({ chat_id: chat.id })
                         });
                         loadChatHistory();
                         // Optionally clear main area if this chat was open
                         if (currentChatId === chat.id) {
                             document.getElementById('messagesContainer').innerHTML = '';
                             document.getElementById('chatTitle').textContent = 'New Chat';
                         }
                     }
                 };
                 chatItem.querySelector('.flex').appendChild(deleteBtn);
                 
                 chatItem.addEventListener('click', function() {
                     loadChat(chat.id);
                 });
                 
                 chatHistory.appendChild(chatItem);
             });
         }
     } catch (error) {
         console.error('Error loading chat history:', error);
     }
 }

 // Load a specific chat
 async function loadChat(chatId) {
     try {
         // Show loading state
         document.getElementById('messagesContainer').innerHTML = `
             <div class="flex justify-center items-center h-full">
                 <div class="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500"></div>
             </div>
         `;
         
         const response = await fetch(`/chat/history?chat_id=${chatId}`);
         const data = await response.json();
         
         if (data.success && data.messages) {
             currentChatId = chatId;
             document.getElementById('chatTitle').textContent = 
                 data.messages.find(m => m.role === 'user')?.content.substring(0, 30) + '...' || 'Chat';
             
             const messagesContainer = document.getElementById('messagesContainer');
             messagesContainer.innerHTML = '';
             
             data.messages.forEach(message => {
                 addMessageToUI(message.content, message.role);
             });
             
             // Highlight active chat in sidebar
             document.querySelectorAll('.chat-item').forEach(item => {
                 item.classList.remove('active');
                 if (item.dataset.chatId === chatId) {
                     item.classList.add('active');
                 }
             });
             
             // Check for PDF context
             checkPdfContext(chatId);
             
             // Scroll to bottom
             messagesContainer.scrollTop = messagesContainer.scrollHeight;
         }
     } catch (error) {
         console.error('Error loading chat:', error);
         addSystemMessage('Error loading chat. Please try again.', 'error');
     }
 }

 // Check if this chat has PDF context
 async function checkPdfContext(chatId) {
     try {
         const response = await fetch(`/chat/pdf-context?chat_id=${chatId}`);
         const data = await response.json();
         
         if (data.success && data.pdf) {
             const pdfIndicator = document.getElementById('pdfIndicator');
             const pdfFilename = document.getElementById('pdfFilename');
             
             pdfIndicator.classList.remove('hidden');
             pdfFilename.textContent = data.pdf.filename;
         } else {
             document.getElementById('pdfIndicator').classList.add('hidden');
         }
     } catch (error) {
         console.error('Error checking PDF context:', error);
     }
 }

 // Start a new chat
 async function startNewChat() {
     try {
         const response = await fetch('/new-chat', {
             method: 'POST',
             headers: {
                 'Content-Type': 'application/json',
             }
         });
         const data = await response.json();
         
         if (data.success) {
             currentChatId = data.chat_id;
             document.getElementById('messagesContainer').innerHTML = `
                 <div class="message flex space-x-4">
                     <div class="flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-r from-purple-500 to-blue-500 flex items-center justify-center text-white">
                         <i class="fas fa-robot"></i>
                     </div>
                     <div class="max-w-3xl bg-gray-700 rounded-lg p-4 shadow-sm">
                         <div class="prose prose-invert max-w-none">
                             <h3>Welcome to Najib & Nabirah AI Chat! 🚀</h3>
                             <p>I'm your advanced AI assistant, ready to help you with:</p>
                             <ul>
                                 <li>💻 Code generation and debugging</li>
                                 <li>📄 PDF document analysis</li>
                                 <li>🤔 Complex problem solving</li>
                                 <li>✍️ Content creation and editing</li>
                                 <li>🧠 Research and explanations</li>
                             </ul>
                             <p>Upload a PDF document or start asking questions. I'm here to help!</p>
                         </div>
                     </div>
                 </div>
             `;
             document.getElementById('chatTitle').textContent = 'New Chat';
             document.getElementById('messageInput').value = '';
             
             // Clear active chat in sidebar
             document.querySelectorAll('.chat-item').forEach(item => {
                 item.classList.remove('active');
             });
             
             // Hide PDF indicator
             document.getElementById('pdfIndicator').classList.add('hidden');
             
             // Refresh chat history
             loadChatHistory();
         }
     } catch (error) {
         console.error('Error starting new chat:', error);
         addSystemMessage('Error starting new chat', 'error');
     }
 }

 // Send a message to the AI
 async function sendMessage() {
     const messageInput = document.getElementById('messageInput');
     const message = messageInput.value.trim();
     
     if (!message || isTyping) return;

     // Add user message to UI
     addMessageToUI(message, 'user');
     messageInput.value = '';
     messageInput.style.height = 'auto';
     
     // Show typing indicator
     showTypingIndicator(true);
     
     try {
         // Create a new EventSource connection for streaming
         if (eventSource) {
             eventSource.close();
         }
         
         const url = new URL('/chat', window.location.origin);
         url.searchParams.append('message', message);
         if (currentChatId) {
             url.searchParams.append('chat_id', currentChatId);
         }
         
         eventSource = new EventSource(url);
         
         let assistantMessage = '';
         let messageElement = null;
         
         eventSource.onmessage = function(event) {
             try {
                 const data = JSON.parse(event.data);
                 
                 if (data.error) {
                     addSystemMessage(data.error, 'error');
                     showTypingIndicator(false);
                     eventSource.close();
                     return;
                 }
                 
                 if (data.content) {
                     assistantMessage += data.content;
                     
                     if (!messageElement) {
                         messageElement = addMessageToUI('', 'assistant');
                         showTypingIndicator(false);
                     }
                     
                     updateMessageContent(messageElement, assistantMessage);
                 }
                 
                 if (data.chat_id && !currentChatId) {
                     currentChatId = data.chat_id;
                     loadChatHistory(); // Refresh chat list
                 }
                 
                 if (data.done) {
                     eventSource.close();
                     eventSource = null;
                     loadChatHistory(); // Refresh chat list after completion
                 }
             } catch (e) {
                 console.error('Error parsing event data:', e);
             }
         };
         
         eventSource.onerror = function() {
             showTypingIndicator(false);
             if (eventSource) {
                 eventSource.close();
                 eventSource = null;
             }
         };
     } catch (error) {
         console.error('Error:', error);
         addSystemMessage('Error sending message. Please try again.', 'error');
         showTypingIndicator(false);
     }
 }

 // Add a message to the UI
 function addMessageToUI(content, role, editable = false) {
     const messagesContainer = document.getElementById('messagesContainer');
     const messageDiv = document.createElement('div');
     messageDiv.className = `message flex space-x-4 ${role === 'user' ? 'justify-end' : ''}`;

     if (role === 'assistant') {
         messageDiv.innerHTML = `
             <div class="flex-shrink-0 w-10 h-10 rounded-full bg-gradient-to-r from-purple-500 to-blue-500 flex items-center justify-center text-white">
                 <i class="fas fa-robot"></i>
             </div>
             <div class="max-w-3xl bg-gray-700 rounded-lg p-4 shadow-sm">
                 <div class="message-content prose prose-invert max-w-none">
                     ${formatMarkdown(content)}
                 </div>
             </div>
         `;
     } else {
         messageDiv.innerHTML = `
             <div class="max-w-3xl bg-blue-600 text-white rounded-lg p-4 shadow-sm flex items-center">
                 <div class="message-content flex-1">${content}</div>
                 <button class="ml-2 text-xs px-2 py-1 bg-gray-700 rounded hover:bg-gray-600" onclick="editPrompt(this)">Edit</button>
             </div>
             <div class="flex-shrink-0 w-10 h-10 rounded-full bg-gray-600 flex items-center justify-center text-white">
                 ${document.getElementById('userAvatar').textContent}
             </div>
         `;
     }
     messagesContainer.appendChild(messageDiv);
     messagesContainer.scrollTop = messagesContainer.scrollHeight;
     
     // Highlight code blocks
     if (role === 'assistant') {
         setTimeout(() => {
             const codeBlocks = messageDiv.querySelectorAll('pre code');
             codeBlocks.forEach(block => {
                 hljs.highlightElement(block);
             });
         }, 100);
     }
     
     return messageDiv;
 }

 // Update message content progressively (for streaming)
 function updateMessageContent(messageElement, content) {
     const messageContent = messageElement.querySelector('.message-content');
     messageContent.innerHTML = formatMarkdown(content);
     
     // Highlight any new code blocks
     setTimeout(() => {
         const codeBlocks = messageContent.querySelectorAll('pre code');
         codeBlocks.forEach(block => {
             if (!block.classList.contains('hljs-highlighted')) {
                 hljs.highlightElement(block);
                 block.classList.add('hljs-highlighted');
             }
         });
     }, 100);
     
     // Scroll to bottom
     messagesContainer.scrollTop = messagesContainer.scrollHeight;
 }

 // Add a system message
 function addSystemMessage(content, type = 'info') {
     const messagesContainer = document.getElementById('messagesContainer');
     const messageDiv = document.createElement('div');
     messageDiv.className = 'flex justify-center my-2';
     
     const messageContent = document.createElement('div');
     messageContent.className = `px-3 py-2 rounded-md text-sm ${
         type === 'error' ? 'bg-red-900 text-red-100' : 'bg-gray-700 text-gray-300'
     }`;
     messageContent.textContent = content;
     
     messageDiv.appendChild(messageContent);
     messagesContainer.appendChild(messageDiv);
     messagesContainer.scrollTop = messagesContainer.scrollHeight;
 }

 // Show/hide typing indicator
 function showTypingIndicator(show) {
     isTyping = show;
     document.getElementById('typingIndicator').style.display = show ? 'block' : 'none';
     document.getElementById('sendButton').disabled = show;
     
     if (show) {
         document.getElementById('messagesContainer').scrollTop = 
             document.getElementById('messagesContainer').scrollHeight;
     }
 }

 // Handle PDF upload
 async function handlePdfUpload(event) {
     const file = event.target.files[0];
     if (!file) return;
     
     const formData = new FormData();
     formData.append('file', file);
     
     try {
         showTypingIndicator(true);
         const response = await fetch('/upload', {
             method: 'POST',
             body: formData
         });
         
         const result = await response.json();
         showTypingIndicator(false);
         
         if (result.success) {
             const pdfIndicator = document.getElementById('pdfIndicator');
             const pdfFilename = document.getElementById('pdfFilename');
             
             pdfIndicator.classList.remove('hidden');
             pdfFilename.textContent = result.filename;
             
             addSystemMessage(`PDF uploaded successfully: ${result.filename}`);
             
             // If we're in a chat, associate this PDF with the current chat
             if (currentChatId) {
                 await fetch('/attach-pdf', {
                     method: 'POST',
                     headers: { 'Content-Type': 'application/json' },
                     body: JSON.stringify({
                         chat_id: currentChatId, // must be set to the active chat
                         file_id: result.file_id
                     })
                 });
             }
         } else {
             addSystemMessage(`Error uploading PDF: ${result.error || 'Unknown error'}`, 'error');
         }
     } catch (error) {
         showTypingIndicator(false);
         addSystemMessage('Network error uploading PDF', 'error');
         console.error('PDF upload error:', error);
     }
     
     // Reset file input
     event.target.value = '';
 }

 // Format date for display
 function formatDate(dateString) {
     const date = new Date(dateString);
     const now = new Date();
     const diff = now - date;
     const days = Math.floor(diff / (1000 * 60 * 60 * 24));
     const hours = Math.floor(diff / (1000 * 60 * 60));
     const minutes = Math.floor(diff / (1000 * 60));
     
     if (days === 0) {
         if (hours === 0) {
             if (minutes < 1) return 'Just now';
             return `${minutes} min ago`;
         }
         return `${hours} hour${hours > 1 ? 's' : ''} ago`;
     } else if (days === 1) {
         return 'Yesterday';
     } else if (days < 7) {
         return `${days} day${days > 1 ? 's' : ''} ago`;
     } else {
         return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
     }
 }

 // Format markdown content
 function formatMarkdown(text) {
     // Convert markdown to HTML
     let html = marked.parse(text || '');
     
     // Add copy buttons to code blocks
     html = html.replace(/<pre><code([^>]*)>([\s\S]*?)<\/code><\/pre>/g, 
         '<div class="code-block-wrapper">' +
         '<div class="code-block-header">' +
         '<button onclick="copyCode(this)" class="copy-button">' +
         '<i class="fas fa-copy"></i> Copy' +
         '</button>' +
         '</div>' +
         '<pre><code$1>$2</code></pre>' +
         '</div>');
     
     return html;
 }

 // Copy code to clipboard
 function copyCode(button) {
     const codeBlock = button.closest('.code-block-wrapper').querySelector('code');
     const text = codeBlock.textContent;
     
     navigator.clipboard.writeText(text).then(() => {
         const originalHTML = button.innerHTML;
         button.innerHTML = '<i class="fas fa-check"></i> Copied!';
         button.classList.add('copied');
         
         setTimeout(() => {
             button.innerHTML = originalHTML;
             button.classList.remove('copied');
         }, 2000);
     }).catch(err => {
         console.error('Failed to copy text: ', err);
     });
 }

 // Logout function
 async function logout() {
     try {
         const response = await fetch('/logout', {
             method: 'POST'
         });
         const data = await response.json();
         
         if (data.success) {
             window.location.href = '/';
         }
     } catch (error) {
         console.error('Logout error:', error);
         window.location.href = '/';
     }
 }

 // Reference to messages container for scrolling
 const messagesContainer = document.getElementById('messagesContainer');

 // Edit prompt functionality
 window.editPrompt = function(button) {
     const messageDiv = button.closest('.message');
     const contentDiv = messageDiv.querySelector('.message-content');
     const oldText = contentDiv.textContent;
     contentDiv.innerHTML = `<textarea class="w-full bg-gray-800 text-white rounded p-2">${oldText}</textarea>
         <button class="mt-2 px-2 py-1 bg-blue-600 rounded" onclick="resendPrompt(this)">Send</button>`;
 };

 window.resendPrompt = async function(button) {
     const textarea = button.parentElement.querySelector('textarea');
     const newText = textarea.value.trim();
     if (!newText) return;
     // Remove old assistant message if present
     const nextMsg = button.closest('.message').nextElementSibling;
     if (nextMsg && nextMsg.classList.contains('message') && nextMsg.querySelector('.fa-robot')) {
         nextMsg.remove();
     }
     // Replace textarea with new message
     button.parentElement.innerHTML = `<div class="message-content">${newText}</div>
         <button class="ml-2 text-xs px-2 py-1 bg-gray-700 rounded hover:bg-gray-600" onclick="editPrompt(this)">Edit</button>`;
     // Send new prompt
     document.getElementById('messageInput').value = newText;
     sendMessage();
 };

 // Theme toggle logic
 function setTheme(dark) {
     const html = document.documentElement;
     if (dark) {
         html.classList.add('dark');
         document.getElementById('themeIcon').className = 'fas fa-moon text-gray-800 dark:text-gray-100';
         document.getElementById('themeLabel').textContent = 'Dark';
         localStorage.setItem('theme', 'dark');
     } else {
         html.classList.remove('dark');
         document.getElementById('themeIcon').className = 'fas fa-sun text-yellow-500';
         document.getElementById('themeLabel').textContent = 'Light';
         localStorage.setItem('theme', 'light');
     }
 }

 // On load, set theme from localStorage or system preference
 document.addEventListener('DOMContentLoaded', function() {
     let dark = localStorage.getItem('theme') === 'dark';
     if (localStorage.getItem('theme') === null) {
         dark = window.matchMedia('(prefers-color-scheme: dark)').matches;
     }
     setTheme(dark);

     document.getElementById('themeToggle').addEventListener('click', function() {
         setTheme(!document.documentElement.classList.contains('dark'));
     });
 });