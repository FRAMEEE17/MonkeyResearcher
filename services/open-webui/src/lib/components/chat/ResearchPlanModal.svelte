<script lang="ts">
	import { createEventDispatcher, onMount } from 'svelte';
	import { fade, fly } from 'svelte/transition';

	export let show = false;
	export let researchTopic = '';
	export let isResearching = false;

	const dispatch = createEventDispatcher();

	// Research plan steps
	const planSteps = [
		{
			id: 1,
			title: 'Query Generation',
			description: 'Generate targeted search queries based on your research topic',
			icon: '🔍',
			status: 'pending'
		},
		{
			id: 2,
			title: 'Web Research',
			description: 'Perform comprehensive web searches and gather information',
			icon: '🌐',
			status: 'pending'
		},
		{
			id: 3,
			title: 'Source Analysis',
			description: 'Analyze and summarize collected sources and data',
			icon: '📊',
			status: 'pending'
		},
		{
			id: 4,
			title: 'Knowledge Gap Assessment',
			description: 'Identify gaps in information and areas needing deeper research',
			icon: '🤔',
			status: 'pending'
		},
		{
			id: 5,
			title: 'Final Synthesis',
			description: 'Compile comprehensive research summary with key findings',
			icon: '✅',
			status: 'pending'
		}
	];

	let currentSteps = [...planSteps];

	// Update step status based on research progress
	export function updateStepStatus(stepId: number, status: 'pending' | 'active' | 'completed') {
		currentSteps = currentSteps.map(step => 
			step.id === stepId ? { ...step, status } : step
		);
	}

	// Map pipeline status to step updates
	export function updateFromPipelineStatus(statusData) {
		if (!statusData?.description) return;
		
		const description = statusData.description.toLowerCase();
		
		// Map status descriptions to step IDs
		if (description.includes('generating') && description.includes('search')) {
			updateStepStatus(1, statusData.done ? 'completed' : 'active');
		} else if (description.includes('research loop') || description.includes('gathering')) {
			updateStepStatus(2, statusData.done ? 'completed' : 'active');
		} else if (description.includes('analyzing') || description.includes('summarizing')) {
			updateStepStatus(3, statusData.done ? 'completed' : 'active');
		} else if (description.includes('gap') || description.includes('identifying')) {
			updateStepStatus(4, statusData.done ? 'completed' : 'active');
		} else if (description.includes('finalizing') || description.includes('complete')) {
			updateStepStatus(5, statusData.done ? 'completed' : 'active');
			if (statusData.done) {
				// Mark all steps as completed when research is done
				currentSteps = currentSteps.map(step => ({ ...step, status: 'completed' }));
				isResearching = false;
			}
		}
	}

	function handleStartResearch() {
		if (!researchTopic.trim()) return;
		
		dispatch('startResearch', {
			topic: researchTopic.trim(),
			steps: currentSteps
		});
	}

	function handleCancel() {
		dispatch('cancel');
		show = false;
	}

	// Reset steps when modal opens
	$: if (show && !isResearching) {
		currentSteps = [...planSteps];
	}

	// Close modal on escape key
	function handleKeydown(e: KeyboardEvent) {
		if (e.key === 'Escape' && show) {
			handleCancel();
		}
	}

	onMount(() => {
		document.addEventListener('keydown', handleKeydown);
		return () => document.removeEventListener('keydown', handleKeydown);
	});
</script>

{#if show}
	<!-- Backdrop -->
	<div
		class="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4"
		transition:fade={{ duration: 200 }}
		on:click={handleCancel}
		role="dialog"
		aria-modal="true"
		aria-labelledby="modal-title"
	>
		<!-- Modal Content -->
		<div
			class="bg-white dark:bg-gray-800 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-y-auto"
			transition:fly={{ y: 20, duration: 300 }}
			on:click|stopPropagation
		>
			<!-- Header -->
			<div class="px-8 py-6 border-b border-gray-200 dark:border-gray-700">
				<div class="flex items-center justify-between">
					<div class="flex items-center space-x-3">
						<div class="w-12 h-12 bg-blue-100 dark:bg-blue-900 rounded-full flex items-center justify-center">
							<span class="text-2xl">🔬</span>
						</div>
						<div>
							<h2 id="modal-title" class="text-2xl font-bold text-gray-900 dark:text-white">
								Deep Research Assistant
							</h2>
							<p class="text-sm text-gray-500 dark:text-gray-400 mt-1">
								AI-powered comprehensive research and analysis
							</p>
						</div>
					</div>
					<button
						on:click={handleCancel}
						class="text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
						aria-label="Close modal"
					>
						<svg class="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
							<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
						</svg>
					</button>
				</div>
			</div>

			<!-- Content -->
			<div class="px-8 py-6">
				<!-- Research Topic Input -->
				<div class="mb-8">
					<label for="research-topic" class="block text-sm font-semibold text-gray-700 dark:text-gray-300 mb-3">
						Research Topic
					</label>
					<div class="relative">
						<input
							id="research-topic"
							type="text"
							bind:value={researchTopic}
							placeholder="Enter your research topic or question..."
							disabled={isResearching}
							class="w-full px-4 py-3 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-600 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-transparent transition-all duration-200 text-gray-900 dark:text-white placeholder-gray-500 dark:placeholder-gray-400 disabled:opacity-50 disabled:cursor-not-allowed"
						/>
						<div class="absolute right-3 top-1/2 transform -translate-y-1/2">
							<span class="text-2xl">🎯</span>
						</div>
					</div>
				</div>

				<!-- Research Plan -->
				<div class="mb-8">
					<h3 class="text-lg font-semibold text-gray-900 dark:text-white mb-4 flex items-center">
						<span class="mr-2">📋</span>
						Research Plan
					</h3>
					<div class="space-y-4">
						{#each currentSteps as step, index}
							<div
								class="flex items-start space-x-4 p-4 rounded-xl transition-all duration-300 {
									step.status === 'active' 
										? 'bg-blue-50 dark:bg-blue-900/20 border-2 border-blue-200 dark:border-blue-700' 
									: step.status === 'completed'
										? 'bg-green-50 dark:bg-green-900/20 border-2 border-green-200 dark:border-green-700'
										: 'bg-gray-50 dark:bg-gray-900/50 border-2 border-gray-200 dark:border-gray-700'
								}"
							>
								<!-- Step Icon & Number -->
								<div class="flex-shrink-0">
									<div
										class="w-10 h-10 rounded-full flex items-center justify-center text-sm font-bold {
											step.status === 'active'
												? 'bg-blue-500 text-white animate-pulse'
											: step.status === 'completed'
												? 'bg-green-500 text-white'
												: 'bg-gray-300 dark:bg-gray-600 text-gray-600 dark:text-gray-300'
										}"
									>
										{#if step.status === 'completed'}
											<svg class="w-5 h-5" fill="currentColor" viewBox="0 0 20 20">
												<path fill-rule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clip-rule="evenodd" />
											</svg>
										{:else if step.status === 'active'}
											<div class="w-3 h-3 bg-white rounded-full animate-bounce"></div>
										{:else}
											{step.id}
										{/if}
									</div>
								</div>

								<!-- Step Content -->
								<div class="flex-1 min-w-0">
									<div class="flex items-center space-x-2 mb-1">
										<span class="text-xl">{step.icon}</span>
										<h4 class="text-base font-semibold text-gray-900 dark:text-white">
											{step.title}
										</h4>
										{#if step.status === 'active'}
											<div class="flex space-x-1">
												<div class="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style="animation-delay: 0ms"></div>
												<div class="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style="animation-delay: 150ms"></div>
												<div class="w-2 h-2 bg-blue-500 rounded-full animate-bounce" style="animation-delay: 300ms"></div>
											</div>
										{/if}
									</div>
									<p class="text-sm text-gray-600 dark:text-gray-400">
										{step.description}
									</p>
								</div>
							</div>
						{/each}
					</div>
				</div>

				<!-- Progress Bar (when researching) -->
				{#if isResearching}
					<div class="mb-6">
						<div class="flex items-center justify-between mb-2">
							<span class="text-sm font-medium text-gray-700 dark:text-gray-300">Research Progress</span>
							<span class="text-sm text-gray-500 dark:text-gray-400">
								{currentSteps.filter(s => s.status === 'completed').length} / {currentSteps.length} completed
							</span>
						</div>
						<div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
							<div
								class="bg-blue-500 h-2 rounded-full transition-all duration-500"
								style="width: {(currentSteps.filter(s => s.status === 'completed').length / currentSteps.length) * 100}%"
							></div>
						</div>
					</div>
				{/if}
			</div>

			<!-- Footer -->
			<div class="px-8 py-6 bg-gray-50 dark:bg-gray-900/50 border-t border-gray-200 dark:border-gray-700 rounded-b-2xl">
				<div class="flex items-center justify-between">
					<div class="text-sm text-gray-500 dark:text-gray-400">
						{#if isResearching}
							<span class="flex items-center">
								<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-blue-500" fill="none" viewBox="0 0 24 24">
									<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
									<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
								</svg>
								Research in progress...
							</span>
						{:else}
							Estimated time: 2-5 minutes
						{/if}
					</div>
					<div class="flex space-x-3">
						<button
							on:click={handleCancel}
							disabled={isResearching}
							class="px-6 py-2 text-gray-600 dark:text-gray-400 hover:text-gray-800 dark:hover:text-gray-200 font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
						>
							{isResearching ? 'Close' : 'Cancel'}
						</button>
						<button
							on:click={handleStartResearch}
							disabled={!researchTopic.trim() || isResearching}
							class="px-8 py-2 bg-blue-500 hover:bg-blue-600 disabled:bg-gray-300 dark:disabled:bg-gray-600 text-white font-semibold rounded-xl transition-all duration-200 transform hover:scale-[1.02] active:scale-[0.98] disabled:cursor-not-allowed disabled:transform-none flex items-center space-x-2"
						>
							{#if isResearching}
								<svg class="animate-spin -ml-1 mr-2 h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
									<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
									<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
								</svg>
								<span>Researching...</span>
							{:else}
								<span>🚀</span>
								<span>Start Research</span>
							{/if}
						</button>
					</div>
				</div>
			</div>
		</div>
	</div>
{/if}

<style>
	/* Custom animations */
	@keyframes bounce {
		0%, 20%, 53%, 80%, 100% {
			transform: translate3d(0, 0, 0);
		}
		40%, 43% {
			transform: translate3d(0, -8px, 0);
		}
		70% {
			transform: translate3d(0, -4px, 0);
		}
		90% {
			transform: translate3d(0, -2px, 0);
		}
	}

	.animate-bounce {
		animation: bounce 1s infinite;
	}
</style>