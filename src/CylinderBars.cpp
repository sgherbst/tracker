// FlyVR
// http://flyvisionlab.weebly.com/
// Contact: Steven Herbst <sherbst@stanford.edu>

#include "Utility.h"
#include "CylinderBars.h"

#define _USE_MATH_DEFINES
#include <math.h>

// Side length of cube.mesh
const double CubeSideLength = 100.0;

CylinderBars::CylinderBars(std::string name, OgreApplication &app, CSimpleIniA &iniFile)
	: name(name), app(app), iniFile(iniFile)
{
	Setup();
}

CylinderBars::~CylinderBars(){
	app.clear();
}

void CylinderBars::Setup(){
	closedLoop = iniFile.GetBoolValue(name.c_str(), "closed-loop", true);

	numSpatialPeriod = iniFile.GetLongValue(name.c_str(), "number-of-periods", 50);
	dutyCycle = iniFile.GetDoubleValue(name.c_str(), "duty-cycle", 0.5);

	// Foreground color definition
	std::string foreColor(iniFile.GetValue(name.c_str(), "foreground-color", "1"));
	foreColorR = getColor(foreColor, ColorType::Red);
	foreColorG = getColor(foreColor, ColorType::Green);
	foreColorB = getColor(foreColor, ColorType::Blue);

	// Background color definition
	std::string backColor(iniFile.GetValue(name.c_str(), "background-color", "0"));
	backColorR = getColor(backColor, ColorType::Red);
	backColorG = getColor(backColor, ColorType::Green);
	backColorB = getColor(backColor, ColorType::Blue);

	waitBefore = iniFile.GetDoubleValue(name.c_str(), "wait-before", 0.55);
	activeDuration = iniFile.GetDoubleValue(name.c_str(), "active-duration", 5.0);
	waitAfter = iniFile.GetDoubleValue(name.c_str(), "wait-after", 0.55);

	rotationSpeed = -1.0 * M_PI / 180.0 * iniFile.GetDoubleValue(name.c_str(), "rotation-speed", 15.0);

	// Less commonly used parameters
	lightHeight = iniFile.GetDoubleValue(name.c_str(), "light-height", 1.25);
	patternRadius = iniFile.GetDoubleValue(name.c_str(), "pattern-radius", 0.8);
	panelHeight = iniFile.GetDoubleValue(name.c_str(), "panel-height", 5);
	panelThickness = iniFile.GetDoubleValue(name.c_str(), "panel-thickness", 0.001);

	// Background light definition
	std::string backLight(iniFile.GetValue(name.c_str(), "background-light", "0"));
	backLightR = getColor(backLight, ColorType::Red);
	backLightG = getColor(backLight, ColorType::Green);
	backLightB = getColor(backLight, ColorType::Blue);

	// Create the scene
	CreateScene();

	// Setup current state
	currentState = CylinderBarStates::Init;
}

void CylinderBars::CreateScene(void){
	// Get scene manager and root node
	auto sceneMgr = app.getSceneManager();
	auto rootNode = sceneMgr->getRootSceneNode();

	// Create node for all stimulus objects
	stimNode = rootNode->createChildSceneNode();

	// Turn on background lighting
	sceneMgr->setAmbientLight(Ogre::ColourValue(backLightR, backLightG, backLightB));

	// Create main light
	auto light = sceneMgr->createLight();
	light->setPosition(Ogre::Real(0), Ogre::Real(lightHeight), Ogre::Real(0));
	stimNode->attachObject(light);

	// Derived scene parameters
	auto dtheta = (2.0 * M_PI) / numSpatialPeriod;
	auto awidth = dutyCycle * dtheta;
	auto xdim = 2 * patternRadius * sin(awidth / 2.0);
	auto ydim = panelHeight;
	auto zdim = panelThickness;

	// Create and attach all stimulus objects
	for (int i = 0; i < numSpatialPeriod; i++){
		// Create node for the panel
		auto panelNode = stimNode->createChildSceneNode();

		// Apply scaling to panel
		auto n = 1.0 / CubeSideLength;
		panelNode->setScale(Ogre::Real(xdim*n), Ogre::Real(ydim*n), Ogre::Real(zdim*n));

		// Calculate angular position of this panel
		auto theta = i*dtheta;

		// Apply position to panel
		auto xpos = patternRadius * sin(theta);
		auto ypos = 0.0;
		auto zpos = -patternRadius * cos(theta);
		panelNode->setPosition(Ogre::Vector3(xpos, ypos, zpos));

		// Apply rotation to panel
		auto pitch = 0.0;
		auto yaw = -theta;
		auto roll = 0.0;
		panelNode->pitch(Ogre::Radian(pitch));
		panelNode->yaw(Ogre::Radian(yaw));
		panelNode->roll(Ogre::Radian(roll));

		// Attach the cube mesh to the panel
		auto panelEnt = sceneMgr->createEntity("cube.mesh");
		panelNode->attachObject(panelEnt);

		// Set the panel color to the desired value
		// TODO: is there a better way to set the color of a panel?
		auto panelColor = Ogre::ColourValue(foreColorR, foreColorG, foreColorB);
		panelEnt->getSubEntity(0)->getMaterial().getPointer()->getTechnique(0)->getPass(0)->setDiffuse(panelColor);
	}
}

void CylinderBars::Update(Pose3D flyPose){
	if (currentState == CylinderBarStates::Init){
		lastTime = std::chrono::high_resolution_clock::now();
		app.setBackground(backColorR, backColorG, backColorB);
		currentState = CylinderBarStates::WaitBefore;
	}
	else if (currentState == CylinderBarStates::WaitBefore){
		auto thisTime = std::chrono::high_resolution_clock::now();
		auto duration = std::chrono::duration<double>(thisTime - lastTime).count();
		if (duration >= waitBefore){
			lastTime = std::chrono::high_resolution_clock::now();
			currentState = CylinderBarStates::Active;
		}
	}
	else if (currentState == CylinderBarStates::Active){
		auto thisTime = std::chrono::high_resolution_clock::now();
		auto duration = std::chrono::duration<double>(thisTime - lastTime).count();

		// Rotate stimulus
		auto rot = duration * rotationSpeed;
		stimNode->setOrientation(stimNode->getInitialOrientation());
		stimNode->yaw(Ogre::Radian(rot));

		// In closed loop, "move the world" so the fly appears to be in the same position
		if (closedLoop){
			auto rootNode = app.getSceneManager()->getRootSceneNode();
			rootNode->setPosition(Ogre::Vector3(flyPose.x, flyPose.y, flyPose.z));
			rootNode->setOrientation(rootNode->getInitialOrientation());
			rootNode->yaw(Ogre::Radian(flyPose.yaw));
		}

		if (duration >= activeDuration){
			lastTime = std::chrono::high_resolution_clock::now();
			currentState = CylinderBarStates::WaitAfter;
		}
	}
	else if (currentState == CylinderBarStates::WaitAfter){
		auto thisTime = std::chrono::high_resolution_clock::now();
		auto duration = std::chrono::duration<double>(thisTime - lastTime).count();

		if (duration >= waitAfter){
			isDone = true;
		}
	}
	else {
		throw std::runtime_error("Invalid CylinderBar state.");
	}
}
