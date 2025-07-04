<script lang="ts">
	import { createEventDispatcher } from 'svelte';

	export let researchTopic = '';
	export let isResearching = false;
	export let progressData = null;

	const dispatch = createEventDispatcher();

	// Research plan steps
	const planSteps = [
		// {
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

	// React to progress data changes
	$: if (progressData) {
		updateFromPipelineStatus(progressData);
	}

	// Animation state for completion
	let showCompletionAnimation = false;
	let showSummary = false;

	// Watch for research completion to trigger animations
	$: {
		const completedCount = currentSteps.filter(step => step.status === 'completed').length;
		if (!isResearching && completedCount === currentSteps.length && currentSteps.length > 0) {
			// Trigger zoom out animation after a brief delay
			setTimeout(() => {
				showCompletionAnimation = true;
				// Show summary after zoom animation
				setTimeout(() => {
					showSummary = true;
				}, 800);
			}, 500);
		}
	}
</script>

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

	@keyframes slideUp {
		from {
			transform: translateY(20px);
			opacity: 0;
		}
		to {
			transform: translateY(0);
			opacity: 1;
		}
	}

	.animate-slide-up {
		animation: slideUp 0.6s ease-out;
	}
</style>