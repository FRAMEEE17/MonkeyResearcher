<script lang="ts">
	import { toast } from 'svelte-sonner';
	import { onMount, getContext, createEventDispatcher } from 'svelte';
	import { fly, fade, scale } from 'svelte/transition';
	import { cubicOut } from 'svelte/easing';
	const i18n = getContext('i18n');
	const dispatch = createEventDispatcher();

	import { artifactCode, chatId, settings, showArtifacts, showControls } from '$lib/stores';
	import { copyToClipboard, createMessagesList } from '$lib/utils';

	import XMark from '../icons/XMark.svelte';
	import ArrowsPointingOut from '../icons/ArrowsPointingOut.svelte';
	import Tooltip from '../common/Tooltip.svelte';
	import SvgPanZoom from '../common/SVGPanZoom.svelte';
	import ArrowLeft from '../icons/ArrowLeft.svelte';
	import ArrowDownTray from '../icons/ArrowDownTray.svelte';

	export let overlay = false;
	export let history;
	let messages = [];

	let contents: Array<{ type: string; content: string }> = [];
	let selectedContentIdx = 0;

	let copied = false;
	let iframeElement: HTMLIFrameElement;

	$: if (history) {
		messages = createMessagesList(history, history.currentId);
		getContents();
	} else {
		messages = [];
		getContents();
	}

	const getContents = () => {
		contents = [];
		messages.forEach((message) => {
			if (message?.role !== 'user' && message?.content) {
				const codeBlockContents = message.content.match(/```[\s\S]*?```/g);
				let codeBlocks = [];

				if (codeBlockContents) {
					codeBlockContents.forEach((block) => {
						const lang = block.split('\n')[0].replace('```', '').trim().toLowerCase();
						const code = block.replace(/```[\s\S]*?\n/, '').replace(/```$/, '');
						codeBlocks.push({ lang, code });
					});
				}

				let htmlContent = '';
				let cssContent = '';
				let jsContent = '';

				codeBlocks.forEach((block) => {
					const { lang, code } = block;

					if (lang === 'html') {
						htmlContent += code + '\n';
					} else if (lang === 'css') {
						cssContent += code + '\n';
					} else if (lang === 'javascript' || lang === 'js') {
						jsContent += code + '\n';
					}
				});

				const inlineHtml = message.content.match(/<html>[\s\S]*?<\/html>/gi);
				const inlineCss = message.content.match(/<style>[\s\S]*?<\/style>/gi);
				const inlineJs = message.content.match(/<script>[\s\S]*?<\/script>/gi);

				if (inlineHtml) {
					inlineHtml.forEach((block) => {
						const content = block.replace(/<\/?html>/gi, ''); // Remove <html> tags
						htmlContent += content + '\n';
					});
				}
				if (inlineCss) {
					inlineCss.forEach((block) => {
						const content = block.replace(/<\/?style>/gi, ''); // Remove <style> tags
						cssContent += content + '\n';
					});
				}
				if (inlineJs) {
					inlineJs.forEach((block) => {
						const content = block.replace(/<\/?script>/gi, ''); // Remove <script> tags
						jsContent += content + '\n';
					});
				}

				// Check for deep research content and create artifact from message text
				if (message.content && (message.content.includes('Deep Research') || message.content.includes('Sources:') || message.content.includes('research'))) {
					// Extract the main content without markdown code blocks
					let researchContent = message.content
						.replace(/```[\s\S]*?```/g, '') // Remove code blocks
						.replace(/^\s*[\r\n]/gm, '') // Remove empty lines
						.trim();
					
					// Convert markdown to HTML with special handling for Sources
					const markdownToHtml = (text) => {
						// Split text into sections - handle multiple source section formats including Thai
						let sourcesIndex = -1;
						const sourcePatterns = [
							'### Sources:',
							'## Sources & References',
							'### Sources & References', 
							'## Sources:',
							'Sources & References',
							'\nSources\n',
							'Sources\n',
							'## แหล่งอ้างอิง',
							'### แหล่งอ้างอิง',
							'แหล่งอ้างอิง',
							'**Sources:**'
						];
						
						// Check for Sources patterns
						for (const pattern of sourcePatterns) {
							sourcesIndex = text.indexOf(pattern);
							if (sourcesIndex !== -1) {
								break;
							}
						}
						
						// Special case: if text starts with "Sources"
						if (sourcesIndex === -1 && text.startsWith('Sources\n')) {
							sourcesIndex = 0;
						}
						
						let mainContent = '';
						let sourcesContent = '';
						
						if (sourcesIndex !== -1) {
							mainContent = text.substring(0, sourcesIndex).trim();
							sourcesContent = text.substring(sourcesIndex).trim();
						} else {
							mainContent = text;
						}
						
						// Track if sources are successfully processed
						let sourcesProcessed = false;
						
						// Process main content with enhanced markdown support
						let processedMain = mainContent
							// Clean up any leftover markdown headers that weren't properly converted
							.replace(/^###+\s*$/gm, '') // Remove standalone ### lines
							.replace(/^##\s*$/gm, '') // Remove standalone ## lines
							.replace(/^#\s*$/gm, '') // Remove standalone # lines
							// Headers (process from most specific to least specific)
							.replace(/^#### (.*$)/gim, '<h4>$1</h4>')
							.replace(/^### (.*$)/gim, '<h3>$1</h3>')
							.replace(/^## (.*$)/gim, '<h2>$1</h2>')
							.replace(/^# (.*$)/gim, '<h1>$1</h1>')
							// Bold and italic
							.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
							.replace(/\*(.*?)\*/g, '<em>$1</em>')
							// Links
							.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>')
							// Bullet points
							.replace(/^\* (.*$)/gim, '<li>$1</li>')
							.replace(/^- (.*$)/gim, '<li>$1</li>')
							// Wrap consecutive list items in ul tags
							.replace(/(<li>.*<\/li>\s*)+/gs, (match) => '<ul>' + match + '</ul>')
							// Horizontal rules
							.replace(/^---$/gm, '<hr>')
							// Convert double line breaks to paragraphs
							.replace(/\n\n/g, '</p><p>')
							// Wrap in paragraph tags if not already wrapped
							.replace(/^(?!<[h1-6ul\/])/gm, '<p>')
							.replace(/(?<!>)$/gm, '</p>')
							// Clean up empty paragraphs and fix nesting
							.replace(/<p><\/p>/g, '')
							.replace(/<p>(<[h1-6])/g, '$1')
							.replace(/(<\/[h1-6]>)<\/p>/g, '$1')
							.replace(/<p>(<ul>)/g, '$1')
							.replace(/(<\/ul>)<\/p>/g, '$1')
							.replace(/<p>(<hr>)<\/p>/g, '$1')
							// Clean up any remaining orphaned markdown symbols
							.replace(/<p>##<\/p>/g, '')
							.replace(/<br>##<br>/g, '')
							.replace(/##<br>/g, '')
							.replace(/<br>##/g, '')
							.replace(/##/g, '')
							// Single line breaks to <br>
							.replace(/\n/g, '<br>');
						
						// Process sources section if it exists
						let processedSources = '';
						if (sourcesContent) {
							// Extract sources from the text - handle multiple formats including Thai headers
							let sourceLines = sourcesContent.split('\n').filter(line => line.trim().startsWith('*'));
							
							// If no asterisk-prefixed lines found, look for alternative formats
							if (sourceLines.length === 0) {
								sourceLines = sourcesContent.split('\n').filter(line => {
									const trimmed = line.trim();
									return trimmed && 
										   !trimmed.startsWith('Sources') && 
										   !trimmed.startsWith('###') &&
										   !trimmed.startsWith('##') &&
										   !trimmed.includes('แหล่งอ้างอิง') && // Skip Thai headers
										   !trimmed.match(/^#+\s/) && // Skip any header lines
										   !trimmed.match(/^\*\*.*\*\*:?\s*$/) && // Skip bold-only lines
										   (trimmed.includes(': http') || trimmed.includes('https://') || trimmed.includes('www.') || 
										    trimmed.includes('(ความน่าเชื่อถือ:') || // Thai reliability indicator
										    trimmed.includes('(Reliability:') || // English reliability indicator
										    trimmed.includes('- ArXiv') || // ArXiv papers
										    trimmed.includes('[http') || // Bracketed URLs
										    trimmed.includes('](http') || // Markdown links
										    trimmed.startsWith('•') || // Bullet points
										    trimmed.startsWith('○') || // Circle bullet points
										    trimmed.startsWith('-') || // Dash bullet points
										    trimmed.includes('ArXiv preprint') || // ArXiv academic format
										    trimmed.includes('Retrieved from') || // Academic citation format
										    (trimmed.match(/^\*\s*[^.]+\.\s*\(\d{4}[a-z]?\)\.\s*\*[^*]+\*\.\s*\[/) && trimmed.includes('(Reliability:')) || // Academic format: Author. (Year). *Title*. [URL]
										    (trimmed.match(/^\*\s*[^:]+:\s*\[http/) && trimmed.includes('(ArXiv Paper)')) || // ArXiv format: Title: [URL] (ArXiv Paper)
										    trimmed.includes('(ArXiv Paper)') || // Any ArXiv paper
										    (trimmed.includes('. (') && trimmed.includes('). *') && trimmed.includes('*. [')) || // Academic citation pattern
										    (trimmed.match(/^[^:]+:\s*https?:\/\//) && trimmed.includes('Reliability:'))); // Plain text with URL and reliability
								});
								// Add * prefix to non-asterisk lines for consistent parsing
								sourceLines = sourceLines.map(line => {
									const trimmed = line.trim();
									// Remove existing bullet points and add asterisk
									return '* ' + trimmed.replace(/^[•○\-]\s*/, '');
								});
							}
							
							if (sourceLines.length > 0) {
								sourcesProcessed = true; // Mark that sources were successfully processed
								processedSources = `
									<div class="sources-section">
										<div class="sources-header" onclick="toggleSources()">
											<h3>Sources used in the report <span class="toggle-icon" id="toggle-icon">▼</span></h3>
										</div>
										<div class="sources-content" id="sources-content">
											${sourceLines.map(line => {
												// Parse each source line - handle different formats
												let match = null;
												
												// Helper function to validate and clean URLs
												const validateAndCleanUrl = (url) => {
													if (!url) return null;
													
													// Remove any leading/trailing whitespace
													url = url.trim();
													
													// Check if it's a valid URL pattern
													if (!url.match(/^https?:\/\//)) {
														// If it doesn't start with http/https, try to add https://
														if (url.includes('.') && !url.includes(' ')) {
															url = 'https://' + url;
														} else {
															return null; // Invalid URL
														}
													}
													
													// Basic URL validation
													try {
														new URL(url);
														return url;
													} catch {
														return null;
													}
												};
												
												// Try multiple formats in order of specificity
												
												// Format 0a: Handle academic citation format: * Author. (Year). *Title*. [URL](URL) (Reliability: Info)
												const academicCitationMatch = line.match(/\*\s*([^.]+\.\s*\(\d{4}[a-z]?\)\.\s*\*[^*]+\*)\.\s*\[([^\]]+)\]\(([^)]+)\)\s*\(([^)]*Reliability[^)]*)\)(.*)$/);
												if (academicCitationMatch) {
													let citation = academicCitationMatch[1].trim();
													let linkText = academicCitationMatch[2].trim();
													let url = academicCitationMatch[3].trim();
													let reliability = academicCitationMatch[4].trim();
													let extra = academicCitationMatch[5].trim();
													
													// Use the full citation as title
													let fullTitle = citation;
													if (reliability) {
														fullTitle += ' (' + reliability + ')';
													}
													if (extra) {
														fullTitle += ' ' + extra;
													}
													match = [academicCitationMatch[0], fullTitle, url];
												}
												
												// Format 0b: Handle ArXiv format: * Title: [URL](URL) (ArXiv Paper)
												if (!match) {
													const arxivMatch = line.match(/\*\s*([^:]+):\s*\[([^\]]+)\]\(([^)]+)\)\s*\(([^)]*ArXiv[^)]*)\)(.*)$/);
													if (arxivMatch) {
														let title = arxivMatch[1].trim();
														let linkText = arxivMatch[2].trim();
														let url = arxivMatch[3].trim();
														let paperType = arxivMatch[4].trim();
														let extra = arxivMatch[5].trim();
														
														// Combine title and paper type
														let fullTitle = title;
														if (paperType) {
															fullTitle += ' (' + paperType + ')';
														}
														if (extra) {
															fullTitle += ' ' + extra;
														}
														match = [arxivMatch[0], fullTitle, url];
													}
												}
												
												// Format 0c: Handle specific format: * **• Title**: URL (Reliability: Info)
												if (!match) {
													const bulletBoldMatch = line.match(/\*\s*\*\*•\s*([^*]+)\*\*:\s*(https?:\/\/[^\s()]+)\s*\(([^)]*Reliability[^)]*)\)(.*)$/);
													if (bulletBoldMatch) {
														let title = bulletBoldMatch[1].trim();
														let url = bulletBoldMatch[2].trim();
														let reliability = bulletBoldMatch[3].trim();
														let extra = bulletBoldMatch[4].trim();
														
														// Combine title and reliability info
														let fullTitle = title;
														if (reliability) {
															fullTitle += ' (' + reliability + ')';
														}
														if (extra) {
															fullTitle += ' ' + extra;
														}
														match = [bulletBoldMatch[0], fullTitle, url];
													}
												}
												
												// Format 0b: Handle plain text format: Title: URL (Reliability: Info)
												if (!match) {
													const plainTextMatch = line.match(/\*\s*([^:]+?):\s*(https?:\/\/[^\s()]+)\s*\(([^)]*Reliability[^)]*)\)(.*)$/);
													if (plainTextMatch) {
														let title = plainTextMatch[1].trim();
														let url = plainTextMatch[2].trim();
														let reliability = plainTextMatch[3].trim();
														let extra = plainTextMatch[4].trim();
														
														// Combine title and reliability info
														let fullTitle = title;
														if (reliability) {
															fullTitle += ' (' + reliability + ')';
														}
														if (extra) {
															fullTitle += ' ' + extra;
														}
														match = [plainTextMatch[0], fullTitle, url];
													}
												}
												
												// Format 1: *   **Title**: Description - URL (Reliability: Info)
												if (!match) {
													const boldWithDashMatch = line.match(/\*\s*\*\*([^*]+)\*\*\s*:\s*([^-]*?)\s*-\s*(https?:\/\/[^\s()]+)(.*)$/);
													if (boldWithDashMatch) {
														let title = boldWithDashMatch[1].trim();
														let description = boldWithDashMatch[2].trim();
														let url = boldWithDashMatch[3].trim();
														let extra = boldWithDashMatch[4].trim();
														
														// Combine title and description, add reliability info
														let fullTitle = title;
														if (description) {
															fullTitle += ' - ' + description;
														}
														if (extra) {
															fullTitle += ' ' + extra;
														}
														match = [boldWithDashMatch[0], fullTitle, url];
													}
												}
												
												// Format 1a: Handle patterns with parentheses and reliability info (Thai and English)
												if (!match) {
													const reliabilityMatch = line.match(/\*\s*([^:]+):\s*(https?:\/\/[^\s()]+)\s*\([^)]*(?:Reliability|ความน่าเชื่อถือ)[^)]*\)(.*)$/);
													if (reliabilityMatch) {
														let title = reliabilityMatch[1].trim();
														let url = reliabilityMatch[2].trim();
														let extra = reliabilityMatch[3].trim();
														
														// Add reliability info to title if present
														if (extra) {
															title += ' ' + extra;
														}
														match = [reliabilityMatch[0], title, url];
													}
												}
												
												// Format 1b: Handle Thai format with reliability info at end
												if (!match) {
													const thaiMatch = line.match(/\*\s*([^:]+):\s*(https?:\/\/[^\s()]+)\s*\(([^)]*ความน่าเชื่อถือ[^)]*)\)(.*)$/);
													if (thaiMatch) {
														let title = thaiMatch[1].trim();
														let url = thaiMatch[2].trim();
														let reliability = thaiMatch[3].trim();
														let extra = thaiMatch[4].trim();
														
														// Clean up title and add reliability info
														title = title.replace(/\*\*/g, ''); // Remove bold markers
														if (reliability) {
															title += ' (' + reliability + ')';
														}
														if (extra) {
															title += ' ' + extra;
														}
														match = [thaiMatch[0], title, url];
													}
												}
												
												if (!match) {
													// Format 1b: Handle patterns with brackets and PDF links
													const bracketMatch = line.match(/\*\s*\*\*([^*]+)\*\*:\s*\[([^\]]+)\]\(([^)]+)\)\s*\([^)]*(?:Reliability|ความน่าเชื่อถือ)[^)]*\)(.*)$/);
													if (bracketMatch) {
														let title = bracketMatch[1].trim();
														let linkText = bracketMatch[2].trim();
														let url = bracketMatch[3].trim();
														let extra = bracketMatch[4].trim();
														
														// Use the title from the bold text, but include link text if different
														let fullTitle = title;
														if (linkText && linkText !== title) {
															fullTitle += ' - ' + linkText;
														}
														if (extra) {
															fullTitle += ' ' + extra;
														}
														match = [bracketMatch[0], fullTitle, url];
													}
												}
												
												if (!match) {
													// Format 2: * **Title**: URL (Reliability: Info) - Handle both Thai and English
													const boldTitleMatch = line.match(/\*\s*\*\*([^*]+)\*\*\s*:\s*(https?:\/\/[^\s()]+)\s*\([^)]*(?:Reliability|ความน่าเชื่อถือ)[^)]*\)(.*)$/);
													if (boldTitleMatch) {
														let title = boldTitleMatch[1].trim();
														let url = boldTitleMatch[2].trim();
														let extra = boldTitleMatch[3].trim();
														
														// Add reliability info to title if present
														if (extra) {
															title += ' ' + extra;
														}
														match = [boldTitleMatch[0], title, url];
													} else {
														// Fallback to general format
														match = line.match(/\*\s*\*\*([^*]+)\*\*\s*:\s*(.+)/);
													}
												}
												
												if (!match) {
													// Format 2b: Handle academic citations with authors
													const academicMatch = line.match(/\*\s*\*\*([^*]+)\*\*\s*\*([^*]+)\*\.\s*\([^)]*(?:Reliability|ความน่าเชื่อถือ)[^)]*\)(.*)$/);
													if (academicMatch) {
														let title = academicMatch[1].trim();
														let publication = academicMatch[2].trim();
														let extra = academicMatch[3].trim();
														
														// For academic citations, we need to extract URL from the publication info
														let url = '';
														const urlMatch = publication.match(/(https?:\/\/[^\s()]+)/);
														if (urlMatch) {
															url = urlMatch[1];
														}
														
														// Combine title and publication info
														let fullTitle = title + ' - ' + publication;
														if (extra) {
															fullTitle += ' ' + extra;
														}
														
														if (url) {
															match = [academicMatch[0], fullTitle, url];
														}
													}
												}
												
												if (!match) {
													// Format 3: * [title](url) - markdown link format
													match = line.match(/\*\s*\[([^\]]+)\]\(([^)]+)\)/);
												}
												
												// Format 3a: Handle complex bold format: * ****Title****: [URL](URL) (ArXiv Paper) (Reliability: Info)
												if (!match) {
													const complexBoldMatch = line.match(/\*\s*\*\*\*\*([^*]+)\*\*\*\*:\s*\[([^\]]+)\]\(([^)]+)\)\s*\(([^)]*)\)\s*\(([^)]*Reliability[^)]*)\)(.*)$/);
													if (complexBoldMatch) {
														let title = complexBoldMatch[1].trim();
														let linkText = complexBoldMatch[2].trim();
														let url = complexBoldMatch[3].trim();
														let paperType = complexBoldMatch[4].trim();
														let reliability = complexBoldMatch[5].trim();
														let extra = complexBoldMatch[6].trim();
														
														// Combine all info
														let fullTitle = title;
														if (paperType) {
															fullTitle += ' (' + paperType + ')';
														}
														if (reliability) {
															fullTitle += ' (' + reliability + ')';
														}
														if (extra) {
															fullTitle += ' ' + extra;
														}
														match = [complexBoldMatch[0], fullTitle, url];
													}
												}
												
												// Format 3b: Handle bullet point format: * Title: URL
												if (!match) {
													const bulletMatch = line.match(/\*\s*([^:]+?):\s*(https?:\/\/[^\s]+)(.*)$/);
													if (bulletMatch) {
														let title = bulletMatch[1].trim();
														let url = bulletMatch[2].trim();
														let extra = bulletMatch[3].trim();
														
														// Clean up title and add extra info if present
														if (extra) {
															title += ' ' + extra;
														}
														match = [bulletMatch[0], title, url];
													}
												}
												
												if (!match) {
													// Format 4: * Title: URL (Reliability: Info) - most common format
													const simpleMatch = line.match(/\*\s*(.+?):\s*(https?:\/\/\S+)(.*)$/);
													if (simpleMatch) {
														let title = simpleMatch[1].trim();
														let url = simpleMatch[2].trim();
														let extra = simpleMatch[3].trim();
														
														// If there's extra text (reliability info), add it to title
														if (extra) {
															title += ' ' + extra;
														}
														match = [simpleMatch[0], title, url];
													} else {
														// Format 4a: Handle Thai format without asterisk: Title: URL (ความน่าเชื่อถือ: Info)
														const thaiSimpleMatch = line.match(/\*\s*([^:]+?):\s*(https?:\/\/\S+)\s*\(([^)]*ความน่าเชื่อถือ[^)]*)\)(.*)$/);
														if (thaiSimpleMatch) {
															let title = thaiSimpleMatch[1].trim();
															let url = thaiSimpleMatch[2].trim();
															let reliability = thaiSimpleMatch[3].trim();
															let extra = thaiSimpleMatch[4].trim();
															
															// Clean up title and add reliability info
															title = title.replace(/\*\*/g, ''); // Remove bold markers
															if (reliability) {
																title += ' (' + reliability + ')';
															}
															if (extra) {
																title += ' ' + extra;
															}
															match = [thaiSimpleMatch[0], title, url];
														} else {
															// Format 4b: Try traditional format: * title : url (with space around colon)
															const spaceColonMatch = line.match(/\*\s*([^:]+?)\s+:\s+(.+)/);
															if (spaceColonMatch) {
																match = [spaceColonMatch[0], spaceColonMatch[1], spaceColonMatch[2]];
															} else {
																// Format 5: Try simple format: * url - title
																const dashMatch = line.match(/\*\s*(.+?)\s*-\s*(.+)/);
																if (dashMatch) {
																	// Swap url and title if first part looks like URL
																	if (dashMatch[1].includes('http') || dashMatch[1].includes('www.')) {
																		match = [dashMatch[0], dashMatch[2], dashMatch[1]];
																	} else {
																		match = [dashMatch[0], dashMatch[1], dashMatch[2]];
																	}
																} else {
																	// Format 6: Try format: title: url (without asterisk) - for fallback
																	const fallbackMatch = line.match(/^([^:]+?):\s*(https?:\/\/.+)/);
																	if (fallbackMatch) {
																		match = [fallbackMatch[0], fallbackMatch[1], fallbackMatch[2]];
																	}
																}
															}
														}
													}
												}
												
												if (match) {
													const title = match[1].trim();
													let url = match[2].trim();
													
													// Validate and clean the URL
													url = validateAndCleanUrl(url);
													if (!url) {
														return ''; // Skip invalid URLs
													}
													
													const domain = extractDomain(url);
													const sourceType = getSourceType(domain, title);
													const iconHtml = getSourceIcon(sourceType, domain);
													
													// Extract reliability information from title
													const reliabilityInfo = extractReliability(title);
													const cleanTitle = reliabilityInfo.cleanTitle;
													const reliabilityBadge = createReliabilityBadge(reliabilityInfo.level, reliabilityInfo.type);
													
													// Escape HTML entities in title and URL to prevent XSS
													const escapeHtml = (str) => {
														return str.replace(/&/g, '&amp;')
																 .replace(/</g, '&lt;')
																 .replace(/>/g, '&gt;')
																 .replace(/"/g, '&quot;')
																 .replace(/'/g, '&#39;');
													};
													
													const escapedTitle = escapeHtml(cleanTitle.replace(/<[^>]+>/g, '').replace(/\*\*/g, ''));
													const escapedUrl = escapeHtml(url);
													
													return `
														<a href="${escapedUrl}" target="_blank" class="source-item" rel="noopener noreferrer">
															${iconHtml}
															<div class="source-content">
																<div class="source-info">
																	<div class="source-domain">${domain}</div>
																	<div class="source-title">${escapedTitle}</div>
																</div>
																${reliabilityBadge}
															</div>
														</a>
													`;
												}
												return '';
											}).join('')}
										</div>
									</div>
								`;
							}
						}
						
						// If sources were processed successfully, don't include them in main content
						// Only show processedSources if we have them, and don't duplicate content
						if (sourcesProcessed && sourcesIndex !== -1) {
							// Return only main content (before sources) + processed sources box
							return processedMain + processedSources;
						} else {
							// Return everything as is if sources weren't processed
							return processedMain + processedSources;
						}
					};
					
					// Helper functions
					const extractDomain = (url) => {
						try {
							// Ensure URL starts with protocol
							const cleanUrl = url.startsWith('http') ? url : 'https://' + url;
							const urlObj = new URL(cleanUrl);
							return urlObj.hostname.replace('www.', '');
						} catch {
							// Fallback: try to extract domain manually
							try {
								const cleanUrl = url.replace(/^https?:\/\//, '').replace(/^www\./, '');
								const domainPart = cleanUrl.split('/')[0].split('?')[0].split('#')[0];
								return domainPart || 'unknown';
							} catch {
								return 'unknown';
							}
						}
					};
					
					const getFaviconUrl = (domain) => {
						return 'https://www.google.com/s2/favicons?sz=32&domain=' + domain;
					};
					
					const getSourceType = (domain, title) => {
						// Academic and research sites
						if (domain.includes('arxiv.org') || domain.includes('paperswithcode.com') || 
							domain.includes('researchgate.net') || domain.includes('ieee.org') ||
							domain.includes('acm.org') || domain.includes('scholar.google') ||
							title.toLowerCase().includes('paper') || title.toLowerCase().includes('arxiv') ||
							title.toLowerCase().includes('research')) {
							return 'paper';
						}
						
						// Documentation sites
						if (domain.includes('docs.') || domain.includes('readthedocs.') || 
							domain.includes('github.io') || domain.includes('gitbook.') ||
							title.toLowerCase().includes('documentation') || title.toLowerCase().includes('docs')) {
							return 'docs';
						}
						
						// Science and data sites
						if (domain.includes('scispace.com') || domain.includes('scinet.usda.gov') ||
							domain.includes('data.') || domain.includes('dataset') ||
							title.toLowerCase().includes('dataset') || title.toLowerCase().includes('data')) {
							return 'science';
						}
						
						// Development and tech sites
						if (domain.includes('github.com') || domain.includes('stackoverflow.com') ||
							domain.includes('npm') || domain.includes('pypi.org')) {
							return 'code';
						}
						
						// News and media sites
						if (domain.includes('medium.com') || domain.includes('news') ||
							domain.includes('blog') || title.toLowerCase().includes('blog')) {
							return 'news';
						}
						
						// Default to web
						return 'web';
					};
					
					const getSourceIcon = (type, domain) => {
						const iconMap = {
							'paper': '<div class="source-icon">📄</div>',
							'docs': '<div class="source-icon">📚</div>',
							'science': '<div class="source-icon">🧪</div>',
							'code': '<div class="source-icon">💻</div>',
							'news': '<div class="source-icon">📰</div>',
							'web': `<img src="${getFaviconUrl(domain)}" alt="${domain}" class="source-icon" onerror="this.innerHTML='🌐'; this.style.display='flex'; this.style.alignItems='center'; this.style.justifyContent='center';">`
						};
						
						return iconMap[type] || iconMap['web'];
					};
					
					const extractReliability = (title) => {
						// Extract reliability information from title
						const reliabilityPattern = /\(([^)]*(?:Reliability|ความน่าเชื่อถือ)[^)]*)\)/i;
						const match = title.match(reliabilityPattern);
						
						if (match) {
							const reliabilityText = match[1];
							const cleanTitle = title.replace(reliabilityPattern, '').trim();
							
							// Extract level (High, Medium, Low)
							let level = 'medium';
							if (reliabilityText.toLowerCase().includes('high') || reliabilityText.includes('สูง')) {
								level = 'high';
							} else if (reliabilityText.toLowerCase().includes('low') || reliabilityText.includes('ต่ำ')) {
								level = 'low';
							}
							
							// Extract type (Official Website, Blog Post, etc.)
							const typeMatch = reliabilityText.match(/(?:High|Medium|Low|สูง|ปานกลาง|ต่ำ)\s*[-–]\s*(.+)/i);
							const type = typeMatch ? typeMatch[1].trim() : '';
							
							return { cleanTitle, level, type, originalText: reliabilityText };
						}
						
						return { cleanTitle: title, level: null, type: '', originalText: '' };
					};
					
					const createReliabilityBadge = (level, type) => {
						if (!level) return '';
						
						const levelConfig = {
							'high': { 
								color: '#10b981', 
								bgColor: '#d1fae5', 
								text: 'High',
								textColor: '#065f46'
							},
							'medium': { 
								color: '#f59e0b', 
								bgColor: '#fef3c7', 
								text: 'Medium',
								textColor: '#92400e'
							},
							'low': { 
								color: '#ef4444', 
								bgColor: '#fee2e2', 
								text: 'Low',
								textColor: '#991b1b'
							}
						};
						
						const config = levelConfig[level] || levelConfig['medium'];
						
						return `
							<div class="reliability-badge" style="
								background-color: ${config.bgColor};
								color: ${config.textColor};
								border: 1px solid ${config.color};
								border-radius: 12px;
								padding: 2px 8px;
								font-size: 11px;
								font-weight: 600;
								margin-top: 4px;
								display: inline-block;
								text-transform: uppercase;
								letter-spacing: 0.025em;
							">
								${config.text}${type ? ' • ' + type : ''}
							</div>
						`;
					};
					
					const renderedContent = `
                        <!DOCTYPE html>
                        <html lang="en">
                        <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
							<!-- MathJax for LaTeX rendering -->
							<script src="https://polyfill.io/v3/polyfill.min.js?features=es6"></${''}script>
							<script id="MathJax-script" async src="https://cdn.jsdelivr.net/npm/mathjax@3/es5/tex-mml-chtml.js"></${''}script>
							<${''}script>
								window.MathJax = {
									tex: {
										inlineMath: [['$', '$'], ['\\\\(', '\\\\)']],
										displayMath: [['$$', '$$'], ['\\\\[', '\\\\]']]
									},
									chtml: {
										scale: 1,
										minScale: 0.5,
										matchFontHeight: false
									}
								};
							</${''}script>
							<${''}style>
								body {
									background-color: white;
									font-family: system-ui, -apple-system, sans-serif;
									line-height: 1.6;
									padding: 20px;
									margin: 0;
									color: #333;
								}
								.research-container {
									max-width: 900px;
									margin: 0 auto;
								}
								.research-title {
									font-size: 28px;
									font-weight: bold;
									color: #2563eb;
									margin-bottom: 30px;
									text-align: center;
									border-bottom: 2px solid #e5e7eb;
									padding-bottom: 15px;
								}
								.research-content {
									font-size: 15px;
									line-height: 1.7;
								}
								h1 {
									color: #1f2937;
									font-size: 24px;
									margin-top: 30px;
									margin-bottom: 15px;
									border-bottom: 1px solid #e5e7eb;
									padding-bottom: 8px;
								}
								h2 {
									color: #374151;
									font-size: 20px;
									margin-top: 25px;
									margin-bottom: 12px;
								}
								h3 {
									color: #4b5563;
									font-size: 18px;
									margin-top: 20px;
									margin-bottom: 10px;
								}
								a {
									color: #2563eb;
									text-decoration: none;
								}
								a:hover {
									text-decoration: underline;
								}
								strong {
									font-weight: 600;
									color: #1f2937;
								}
								em {
									font-style: italic;
									color: #4b5563;
								}
								.math {
									margin: 10px 0;
								}
								p {
									margin-bottom: 15px;
								}
								
								/* Sources Section Styles */
								.sources-section {
									margin-top: 40px;
									border: 1px solid #e5e7eb;
									border-radius: 12px;
									overflow: hidden;
									background: #ffffff;
									box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1), 0 1px 2px 0 rgba(0, 0, 0, 0.06);
								}
								
								.sources-header {
									background: #f8fafc;
									padding: 16px 20px;
									cursor: pointer;
									border-bottom: 1px solid #e2e8f0;
									user-select: none;
									transition: all 0.2s ease;
								}
								
								.sources-header:hover {
									background: #f1f5f9;
								}
								
								.sources-header h3 {
									margin: 0;
									font-size: 15px;
									font-weight: 600;
									color: #334155;
									display: flex;
									align-items: center;
									justify-content: space-between;
									letter-spacing: -0.025em;
								}
								
								.toggle-icon {
									font-size: 14px;
									transition: transform 0.3s ease;
									color: #64748b;
									margin-left: 8px;
								}
								
								.toggle-icon.collapsed {
									transform: rotate(-90deg);
								}
								
								.sources-content {
									max-height: 500px;
									overflow-y: auto;
									transition: max-height 0.4s ease, opacity 0.3s ease;
									background: #ffffff;
								}
								
								.sources-content.collapsed {
									max-height: 0;
									opacity: 0;
									overflow: hidden;
								}
								
								.source-item {
									display: flex;
									align-items: flex-start;
									padding: 14px 20px;
									border-bottom: 1px solid #f1f5f9;
									transition: all 0.2s ease;
									text-decoration: none;
									color: inherit;
									cursor: pointer;
									gap: 12px;
								}
								
								.source-item:last-child {
									border-bottom: none;
								}
								
								.source-item:hover {
									background: #f8fafc;
									text-decoration: none;
								}
								
								.source-icon {
									width: 24px;
									height: 24px;
									border-radius: 6px;
									flex-shrink: 0;
									margin-top: 2px;
									background: #f1f5f9;
									display: flex;
									align-items: center;
									justify-content: center;
									font-size: 12px;
									font-weight: 600;
									color: #64748b;
								}
								
								.source-content {
									flex: 1;
									min-width: 0;
									display: flex;
									align-items: center;
									gap: 12px;
								}

								.source-info {
                                    flex: 1;
                                    min-width: 0;
                                    display: flex;
                                    flex-direction: column;
                                    gap: 2px;
                                }
								
								.source-domain {
                                    font-size: 13px;
                                    font-weight: 600;
                                    color: #475569;
                                    text-decoration: none;
                                    letter-spacing: -0.025em;
                                }
								
								.source-title {
                                    font-size: 14px;
                                    color: #64748b;
                                    line-height: 1.4;
                                    overflow: hidden;
                                    display: -webkit-box;
                                    -webkit-line-clamp: 2;
                                    -webkit-box-orient: vertical;
                                    font-weight: 400;
                                }
								
								.source-item:hover .source-domain {
									color: #334155;
								}
								
								.source-item:hover .source-title {
									color: #475569;
								}
								
								/* Hide unwanted elements */
								.research-content > h1:nth-child(1) {
									display: none !important;
								}
								
								.research-content > p:nth-child(3) > strong:nth-child(1) {
									display: none !important;
								}
								
								.research-content > p:nth-child(3){
									display: none !important;
								}
							</${''}style>
                        </head>
                        <body>
                            <div class="research-container">
								<div class="research-content">${markdownToHtml(researchContent)}</div>
							</div>
							
							<${''}script>
								function toggleSources() {
									const content = document.getElementById('sources-content');
									const icon = document.getElementById('toggle-icon');
									
									if (content && icon) {
										if (content.classList.contains('collapsed')) {
											content.classList.remove('collapsed');
											icon.classList.remove('collapsed');
											icon.textContent = '▼';
										} else {
											content.classList.add('collapsed');
											icon.classList.add('collapsed');
											icon.textContent = '▶';
										}
									}
								}
								
								// Initialize sources as expanded by default
								document.addEventListener('DOMContentLoaded', function() {
									const content = document.getElementById('sources-content');
									const icon = document.getElementById('toggle-icon');
									if (content && icon) {
										content.classList.remove('collapsed');
										icon.classList.remove('collapsed');
									}
								});
							</${''}script>
                        </body>
                        </html>
                    `;
					contents = [...contents, { type: 'iframe', content: renderedContent }];
				} else if (htmlContent || cssContent || jsContent) {
					const renderedContent = `
                        <!DOCTYPE html>
                        <html lang="en">
                        <head>
                            <meta charset="UTF-8">
                            <meta name="viewport" content="width=device-width, initial-scale=1.0">
							<${''}style>
								body {
									background-color: white; /* Ensure the iframe has a white background */
								}

								${cssContent}
							</${''}style>
                        </head>
                        <body>
                            ${htmlContent}

							<${''}script>
                            	${jsContent}
							</${''}script>
                        </body>
                        </html>
                    `;
					contents = [...contents, { type: 'iframe', content: renderedContent }];
				} else {
					// Check for SVG content
					for (const block of codeBlocks) {
						if (block.lang === 'svg' || (block.lang === 'xml' && block.code.includes('<svg'))) {
							contents = [...contents, { type: 'svg', content: block.code }];
						}
					}
				}
			}
		});

		if (contents.length === 0) {
			showControls.set(false);
			showArtifacts.set(false);
		}

		selectedContentIdx = contents ? contents.length - 1 : 0;
	};

	function navigateContent(direction: 'prev' | 'next') {
		console.log(selectedContentIdx);

		selectedContentIdx =
			direction === 'prev'
				? Math.max(selectedContentIdx - 1, 0)
				: Math.min(selectedContentIdx + 1, contents.length - 1);

		console.log(selectedContentIdx);
	}

	const iframeLoadHandler = () => {
		iframeElement.contentWindow.addEventListener(
			'click',
			function (e) {
				const target = e.target.closest('a');
				if (target && target.href) {
					e.preventDefault();
					// Check if the URL is already absolute to avoid resolving it relative to base URI
					const url = target.href.startsWith('http://') || target.href.startsWith('https://') 
						? new URL(target.href) 
						: new URL(target.href, iframeElement.baseURI);
					if (url.origin === window.location.origin) {
						iframeElement.contentWindow.history.pushState(
							null,
							'',
							url.pathname + url.search + url.hash
						);
					} else {
						console.info('External navigation blocked:', url.href);
					}
				}
			},
			true
		);

		// Cancel drag when hovering over iframe
		iframeElement.contentWindow.addEventListener('mouseenter', function (e) {
			e.preventDefault();
			iframeElement.contentWindow.addEventListener('dragstart', (event) => {
				event.preventDefault();
			});
		});
	};

	const showFullScreen = () => {
		if (iframeElement.requestFullscreen) {
			iframeElement.requestFullscreen();
		} else if (iframeElement.webkitRequestFullscreen) {
			iframeElement.webkitRequestFullscreen();
		} else if (iframeElement.msRequestFullscreen) {
			iframeElement.msRequestFullscreen();
		}
	};

	const downloadArtifact = () => {
		const blob = new Blob([contents[selectedContentIdx].content], { type: 'text/html' });
		const url = URL.createObjectURL(blob);
		const a = document.createElement('a');
		a.href = url;
		a.download = `artifact-${$chatId}-${selectedContentIdx}.html`;
		document.body.appendChild(a);
		a.click();
		document.body.removeChild(a);
		URL.revokeObjectURL(url);
	};

	onMount(() => {
		artifactCode.subscribe((value) => {
			if (contents) {
				const codeIdx = contents.findIndex((content) => content.content.includes(value));
				selectedContentIdx = codeIdx !== -1 ? codeIdx : 0;
			}
		});
	});
</script>

<div 
	class=" w-full h-full relative flex flex-col bg-gray-50 dark:bg-gray-850"
	in:fly="{{ x: 300, duration: 400, easing: cubicOut }}"
	out:fly="{{ x: 300, duration: 300, easing: cubicOut }}"
>
	<div class="w-full h-full flex flex-col flex-1 relative">
		{#if contents.length > 0}
			<div
				class="pointer-events-auto z-20 flex justify-between items-center p-2.5 font-primar text-gray-900 dark:text-white"
				in:scale="{{ duration: 200, start: 0.95, easing: cubicOut }}"
			>
				<button
					class="self-center pointer-events-auto p-1 rounded-full bg-white dark:bg-gray-850"
					on:click={() => {
						showArtifacts.set(false);
					}}
				>
					<ArrowLeft className="size-3.5  text-gray-900 dark:text-white" />
				</button>

				<div class="flex-1 flex items-center justify-between pr-1">
					<div class="flex items-center space-x-2">
						<div class="flex items-center gap-0.5 self-center min-w-fit" dir="ltr">
							<button
								class="self-center p-1 hover:bg-black/5 dark:hover:bg-white/5 dark:hover:text-white hover:text-black rounded-md transition disabled:cursor-not-allowed"
								on:click={() => navigateContent('prev')}
								disabled={contents.length <= 1}
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
									stroke-width="2.5"
									class="size-3.5"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="M15.75 19.5 8.25 12l7.5-7.5"
									/>
								</svg>
							</button>

							<div class="text-xs self-center dark:text-gray-100 min-w-fit">
								{$i18n.t('Version {{selectedVersion}} of {{totalVersions}}', {
									selectedVersion: selectedContentIdx + 1,
									totalVersions: contents.length
								})}
							</div>

							<button
								class="self-center p-1 hover:bg-black/5 dark:hover:bg-white/5 dark:hover:text-white hover:text-black rounded-md transition disabled:cursor-not-allowed"
								on:click={() => navigateContent('next')}
								disabled={contents.length <= 1}
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									fill="none"
									viewBox="0 0 24 24"
									stroke="currentColor"
									stroke-width="2.5"
									class="size-3.5"
								>
									<path
										stroke-linecap="round"
										stroke-linejoin="round"
										d="m8.25 4.5 7.5 7.5-7.5 7.5"
									/>
								</svg>
							</button>
						</div>
					</div>

					<div class="flex items-center gap-1.5">
						<button
							class="copy-code-button bg-none border-none text-xs bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 transition rounded-md px-1.5 py-0.5"
							on:click={() => {
								copyToClipboard(contents[selectedContentIdx].content);
								copied = true;

								setTimeout(() => {
									copied = false;
								}, 2000);
							}}>{copied ? $i18n.t('Copied') : $i18n.t('Copy')}</button
						>

						<Tooltip content={$i18n.t('Download')}>
							<button
								class=" bg-none border-none text-xs bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 transition rounded-md p-0.5"
								on:click={downloadArtifact}
							>
								<ArrowDownTray className="size-3.5" />
							</button>
						</Tooltip>

						{#if contents[selectedContentIdx].type === 'iframe'}
							<Tooltip content={$i18n.t('Open in full screen')}>
								<button
									class=" bg-none border-none text-xs bg-gray-50 hover:bg-gray-100 dark:bg-gray-850 dark:hover:bg-gray-800 transition rounded-md p-0.5"
									on:click={showFullScreen}
								>
									<ArrowsPointingOut className="size-3.5" />
								</button>
							</Tooltip>
						{/if}
					</div>
				</div>

				<button
					class="self-center pointer-events-auto p-1 rounded-full bg-white dark:bg-gray-850"
					on:click={() => {
						dispatch('close');
						showControls.set(false);
						showArtifacts.set(false);
					}}
				>
					<XMark className="size-3.5 text-gray-900 dark:text-white" />
				</button>
			</div>
		{/if}

		{#if overlay}
			<div class=" absolute top-0 left-0 right-0 bottom-0 z-10"></div>
		{/if}

		<div class="flex-1 w-full h-full">
			<div class=" h-full flex flex-col">
				{#if contents.length > 0}
					<div class="max-w-full w-full h-full" in:fade="{{ duration: 300, delay: 200 }}">
						{#if contents[selectedContentIdx].type === 'iframe'}
							<iframe
								bind:this={iframeElement}
								title="Content"
								srcdoc={contents[selectedContentIdx].content}
								class="w-full border-0 h-full rounded-none"
								sandbox="allow-scripts allow-downloads{($settings?.iframeSandboxAllowForms ?? false)
									? ' allow-forms'
									: ''}{($settings?.iframeSandboxAllowSameOrigin ?? false)
									? ' allow-same-origin'
									: ''}"
								on:load={iframeLoadHandler}
							></iframe>
						{:else if contents[selectedContentIdx].type === 'svg'}
							<SvgPanZoom
								className=" w-full h-full max-h-full overflow-hidden"
								svg={contents[selectedContentIdx].content}
							/>
						{/if}
					</div>
				{:else}
					<div class="m-auto font-medium text-xs text-gray-900 dark:text-white">
						{$i18n.t('No HTML, CSS, or JavaScript content found.')}
					</div>
				{/if}
			</div>
		</div>
	</div>
</div>
