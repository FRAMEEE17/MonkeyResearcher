<script lang="ts">
	import { createEventDispatcher, onMount, onDestroy } from 'svelte';
	import { fade, fly, slide } from 'svelte/transition';

	export let pipelineId = '';
	export let statusData = null;
	export let statusHistory = [];
	export let isActive = false;

	let isCollapsed = false;
	let showCollapsedDelay: number;

	const dispatch = createEventDispatcher();

	interface ProgressStep {
		id: string;
		description: string;
		timestamp: number;
		status: 'active' | 'completed' | 'pending';
		duration?: number;
	}

	let progressSteps: ProgressStep[] = [];
	let currentStep: ProgressStep | null = null;
	let totalSteps = 0;
	let completedSteps = 0;
	let startTime = Date.now();

	// Map status descriptions to progress indicators
	const statusIconMap = {
		'starting': '🚀',
		'generating': '🔍',
		'searching': '🌐',
		'research': '🌐',
		'analyzing': '📊',
		'summarizing': '📊',
		'reflecting': '🤔',
		'identifying': '🤔',
		'finalizing': '✅',
		'complete': '✅',
		'error': '❌'
	};

	function getStatusIcon(description: string): string {
		const lowerDesc = description.toLowerCase();
		for (const [key, icon] of Object.entries(statusIconMap)) {
			if (lowerDesc.includes(key)) {
				return icon;
			}
		}
		return '⚡';
	}

	function addProgressStep(description: string, done: boolean = false) {
		const now = Date.now();
		const stepId = `step-${progressSteps.length}`;
		
		// Mark previous step as completed if there was one
		if (currentStep && !done) {
			const completedStep = {
				...currentStep,
				status: 'completed' as const,
				duration: now - currentStep.timestamp
			};
			progressSteps = progressSteps.map(step => 
				step.id === currentStep.id ? completedStep : step
			);
			completedSteps++;
		}

		const newStep: ProgressStep = {
			id: stepId,
			description,
			timestamp: now,
			status: done ? 'completed' : 'active'
		};

		progressSteps = [...progressSteps, newStep];
		
		if (done) {
			// Mark current step as completed when done
			if (currentStep) {
				const completedCurrentStep = {
					...currentStep,
					status: 'completed' as const,
					duration: now - currentStep.timestamp
				};
				progressSteps = progressSteps.map(step => 
					step.id === currentStep.id ? completedCurrentStep : step
				);
				completedSteps++;
			}
			// Mark the new step as completed too
			const completedNewStep = {
				...newStep,
				status: 'completed' as const,
				duration: 0
			};
			progressSteps = progressSteps.map(step => 
				step.id === newStep.id ? completedNewStep : step
			);
			completedSteps++;
			currentStep = null;
		} else {
			currentStep = newStep;
		}
		
		totalSteps = progressSteps.length;
	}

	function formatDuration(duration: number): string {
		if (duration < 1000) return `${duration}ms`;
		const seconds = Math.floor(duration / 1000);
		if (seconds < 60) return `${seconds}s`;
		const minutes = Math.floor(seconds / 60);
		const remainingSeconds = seconds % 60;
		return `${minutes}m ${remainingSeconds}s`;
	}

	function getElapsedTime(): string {
		return formatDuration(Date.now() - startTime);
	}

	// Initialize progress from status history
	function initializeFromHistory() {
		if (statusHistory && statusHistory.length > 0) {
			progressSteps = [];
			completedSteps = 0;
			currentStep = null;
			
			statusHistory.forEach(status => {
				if (status.description && status.description.trim()) {
					addProgressStep(status.description, status.done || false);
				}
			});
		}
	}

	// React to status data changes
	$: if (statusData) {
		const description = statusData.description || '';
		const done = statusData.done || false;
		
		if (description && description.trim()) {
			// Check if this status is already in our progress steps
			const existingStep = progressSteps.find(step => step.description === description);
			if (!existingStep) {
				addProgressStep(description, done);
			}
		}
	}

	// React to status history changes
	$: if (statusHistory && statusHistory.length > 0) {
		initializeFromHistory();
	}

	// Auto-collapse when research is complete
	$: if (!isActive && completedSteps === totalSteps && totalSteps > 0) {
		// Delay collapse by 3 seconds after completion
		if (showCollapsedDelay) {
			clearTimeout(showCollapsedDelay);
		}
		showCollapsedDelay = setTimeout(() => {
			isCollapsed = true;
		}, 3000);
	}

	// Auto-refresh elapsed time every second when active
	let timeInterval: number;
	
	onMount(() => {
		if (isActive) {
			timeInterval = setInterval(() => {
				// Force reactivity update for elapsed time
				progressSteps = [...progressSteps];
			}, 1000);
		}
	});

	onDestroy(() => {
		if (timeInterval) {
			clearInterval(timeInterval);
		}
		if (showCollapsedDelay) {
			clearTimeout(showCollapsedDelay);
		}
	});

	$: if (isActive && !timeInterval) {
		timeInterval = setInterval(() => {
			progressSteps = [...progressSteps];
		}, 1000);
	} else if (!isActive && timeInterval) {
		clearInterval(timeInterval);
		timeInterval = null;
	}
</script>

<div class="real-time-progress w-full max-w-md text-gray-500 dark:text-gray-500 text-base transition-all duration-300 {isCollapsed ? 'p-2 bg-gray-50 dark:bg-gray-800 rounded-full' : 'p-4 bg-gray-50 dark:bg-gray-800 rounded-lg'}">
	<!-- Header -->
	<div class="flex items-center justify-between {isCollapsed ? 'mb-0' : 'mb-4'}">
		<div class="flex items-center gap-2 flex-1 min-w-0">
			<!-- Collapse/Expand button -->
			{#if !isActive && totalSteps > 0}
				<button 
					class="flex items-center justify-center w-4 h-4 text-gray-400 hover:text-gray-600 dark:hover:text-gray-300 transition-colors"
					on:click={() => isCollapsed = !isCollapsed}
					aria-label={isCollapsed ? 'Expand progress' : 'Collapse progress'}
				>
					{#if isCollapsed}
						<span class="text-xs">▶</span>
					{:else}
						<span class="text-xs">▼</span>
					{/if}
				</button>
			{/if}
			<div class="flex-1 min-w-0">
				<h3 class="text-xs text-gray-500 dark:text-gray-500 line-clamp-1 text-wrap {isActive ? 'shimmer' : ''}">
					{#if isCollapsed}
						<span class="text-xs text-gray-400 dark:text-gray-500">Research Complete ({completedSteps}/{totalSteps})</span>
					{:else if currentStep && currentStep.description}
						{currentStep.description}
					{:else if statusData && statusData.description}
						{statusData.description}
					{:else}
						Pipeline Progress
					{/if}
				</h3>
			</div>
		</div>
		{#if totalSteps > 0 && !isCollapsed}
			<div class="text-xs text-gray-500 dark:text-gray-400 ml-2">
				{completedSteps}/{totalSteps}
			</div>
		{/if}
	</div>

	{#if !isCollapsed}
		<div transition:slide="{{ duration: 300 }}">
			<!-- Progress Bar -->
			{#if totalSteps > 0}
				<div class="mb-4">
					<div class="w-full bg-gray-200 dark:bg-gray-700 rounded-full h-2">
						<div 
							class="bg-blue-500 h-2 rounded-full transition-all duration-300 ease-out"
							style="width: {totalSteps > 0 ? (completedSteps / totalSteps) * 100 : 0}%"
						></div>
					</div>
				</div>
			{/if}

			<!-- Progress Steps -->
			<div class="space-y-2 max-h-64 overflow-y-auto">
			{#each progressSteps as step, index (step.id)}
				<div 
					class="flex items-start gap-3 p-2 rounded-md transition-all duration-200 {step.status === 'active' ? 'bg-blue-50 dark:bg-blue-900/20' : ''} {step.status === 'completed' ? 'bg-green-50 dark:bg-green-900/20' : ''}"
					in:fly="{{ y: 20, duration: 300, delay: index * 50 }}"
				>
					<!-- Status Icon -->
					<div class="flex-shrink-0 mt-0.5">
						{#if step.status === 'active'}
							<div class="w-4 h-4 text-sm animate-spin">⚡</div>
						{:else if step.status === 'completed'}
							<!-- <div class="w-4 h-4 text-sm">{step.description}</div> -->
						{:else}
							<div class="w-4 h-4 text-sm opacity-50">⚪</div>
						{/if}
					</div>

					<!-- Step Content -->
					<div class="flex-1 min-w-0">
						<div class="text-sm text-gray-800 dark:text-gray-200 font-medium">
							{step.description}
						</div>
						<!-- <div class="text-xs text-gray-500 dark:text-gray-400 mt-1">
							{#if step.status === 'completed' && step.duration}
								Completed in {formatDuration(step.duration)}
							{:else if step.status === 'active'}
								{formatDuration(Date.now() - step.timestamp)} elapsed
							{:else}
								{new Date(step.timestamp).toLocaleTimeString()}
							{/if}
						</div> -->
					</div>

					<!-- Status Indicator -->
					<div class="flex-shrink-0">
						{#if step.status === 'active'}
							<div class="w-2 h-2 bg-blue-500 rounded-full animate-pulse"></div>
						{:else if step.status === 'completed'}
							<div class="w-2 h-2 bg-green-500 rounded-full"></div>
						{:else}
							<div class="w-2 h-2 bg-gray-300 dark:bg-gray-600 rounded-full"></div>
						{/if}
					</div>
				</div>
			{/each}
		</div>

		<!-- Footer -->
		{#if progressSteps.length > 0}
			<div class="mt-4 pt-3 border-t border-gray-200 dark:border-gray-700">
				<div class="flex justify-between items-center text-xs text-gray-500 dark:text-gray-400">
					<span>Total elapsed: {getElapsedTime()}</span>
					{#if !isActive && completedSteps === totalSteps}
						<span class="text-green-600 dark:text-green-400 font-medium">✅ Complete</span>
					{:else if isActive}
						<span class="text-blue-600 dark:text-blue-400 font-medium animate-pulse">⚡ Active</span>
					{/if}
				</div>
			</div>
		{/if}

			<!-- Empty State -->
			{#if progressSteps.length === 0}
				<div class="text-center py-8 text-gray-500 dark:text-gray-400">
					<div class="text-2xl mb-2">⏳</div>
					<div class="text-sm">Waiting for pipeline to start...</div>
				</div>
			{/if}
		</div>
	{/if}
</div>

<style>
	.real-time-progress {
		font-family: system-ui, -apple-system, sans-serif;
	}
	
	.real-time-progress::-webkit-scrollbar {
		width: 4px;
	}
	
	.real-time-progress::-webkit-scrollbar-track {
		background: transparent;
	}
	
	.real-time-progress::-webkit-scrollbar-thumb {
		background: rgba(156, 163, 175, 0.5);
		border-radius: 2px;
	}
	
	.real-time-progress::-webkit-scrollbar-thumb:hover {
		background: rgba(156, 163, 175, 0.7);
	}
</style>